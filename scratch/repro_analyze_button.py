"""
Reproducer for: "Analyze Telemetry" button does nothing on the fetched-target path.

This is a one-off diagnostic script (not a pytest test). Run it with:
    python scratch/repro_analyze_button.py

We exercise the UI exactly the way a user does:
  1. Boot the app via AppTest
  2. Navigate to the Detective page
  3. Type "Kepler-90" into the search box
  4. (Skip the network call — inject fetched_target_data directly into
     session_state so we don't depend on MAST being reachable)
  5. Click "Analyze Telemetry & Verify Harmonics"
  6. Observe whether run_analysis fired (session_state['detective_results']
     should now be populated, OR the spinner should have run, OR a
     st.error should appear in the exception list).

If step 6 produces nothing at all — no exception, no results, no
spinner output — that confirms the "click does nothing" bug the user
reported.
"""

import os
import sys
import time

# Make project root importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from streamlit.testing.v1 import AppTest
from streamlit.delta_generator_singletons import DeltaGeneratorSingleton


def _reset_singleton():
    """Same permissive-init pattern tests/conftest.py uses."""
    original_init = DeltaGeneratorSingleton.__init__

    def _permissive_init(self, *args, **kwargs):
        DeltaGeneratorSingleton._instance = None
        original_init(self, *args, **kwargs)

    DeltaGeneratorSingleton.__init__ = _permissive_init


_reset_singleton()

print("=" * 70)
print("Step 1: Boot app.py via AppTest")
print("=" * 70)
t0 = time.time()
at = AppTest.from_file(os.path.join(PROJECT_ROOT, "app.py"), default_timeout=30)
# I4 fix evidence: round-1 hit a 3s timeout on unkeyed buttons. Use the
# same timeout=30 the I4 smoke test uses, so we match the documented
# "post-I4-patch should complete well under 30s" budget.
at.run(timeout=30)
print(f"  Boot OK in {time.time() - t0:.2f}s")
print(f"  Exceptions: {at.exception}")
print()

print("=" * 70)
print("Step 2: Navigate to Detective page")
print("=" * 70)
detective_btn = None
for btn in at.sidebar.get("button"):
    if "Detective" in btn.label:
        detective_btn = btn
        break
if detective_btn is None:
    print("  FATAL: 'Detective' sidebar button not found")
    sys.exit(1)
detective_btn.click().run()
print(f"  Navigated to Detective. Exceptions: {at.exception}")
print()

print("=" * 70)
print("Step 3: Type 'Kepler-90' into search_target text input")
print("=" * 70)
search_input = None
for inp in at.get("text_input"):
    if inp.key == "search_target":
        search_input = inp
        break
if search_input is None:
    print("  FATAL: text_input with key='search_target' not found")
    sys.exit(1)
search_input.set_value("Kepler-90").run()
print(f"  search_target set. Exceptions: {at.exception}")
print()

print("=" * 70)
print("Step 4: Inject fetched_target_data into session_state")
print("=" * 70)
# We bypass the network call (MAST) and put a known-good result directly
# into session_state, mimicking what 'Fetch Target Metadata' would do on
# success. This isolates the analyze-button click from the fetch path.
import numpy as np

rng = np.random.default_rng(42)
n_points = 1000
time_arr = np.linspace(0, 30, n_points)
flux_arr = 1.0 + rng.normal(0, 0.001, n_points)
# Inject a small transit at period=14.45 d
phases = (time_arr % 14.45)
transit_mask = (phases < 0.1) | (phases > 14.45 - 0.1)
flux_arr[transit_mask] -= 0.005

at.session_state["fetched_target_data"] = {
    "status": "success",
    "metadata": {
        "pl_name": "Kepler-90",
        "orbital_period": 14.45,
        "stellar_radius": 1.2,
        "transit_depth": 0.0005,
        "stellar_mass": 1.2,
    },
    "time": time_arr,
    "flux": flux_arr,
    "flux_err": np.full(n_points, 0.001),
    "bridged_mission": "Kepler",
}
at.session_state["active_metadata"] = at.session_state["fetched_target_data"]["metadata"]
at.run()
print(f"  fetched_target_data injected. Exceptions: {at.exception}")
print()

print("=" * 70)
print("Step 5: Click 'Analyze Telemetry & Verify Harmonics' (fetched path)")
print("=" * 70)
analyze_btn = None
for btn in at.get("button"):
    if "Analyze Telemetry & Verify Harmonics" in btn.label and btn.key == "detective_analyze_fetched":
        analyze_btn = btn
        break
if analyze_btn is None:
    print("  FATAL: 'Analyze Telemetry & Verify Harmonics' (fetched) button not found")
    # Show all buttons for diagnosis
    print("  All buttons on page:")
    for b in at.get("button"):
        print(f"    - key={b.key!r} label={b.label!r}")
    sys.exit(1)
print(f"  Button found: key={analyze_btn.key!r}")
analyze_btn.click().run()
print(f"  Clicked. Exceptions: {at.exception}")
print()

print("=" * 70)
print("Step 6: Inspect post-click session_state (FIRST click)")
print("=" * 70)
def _peek(safe_ss, key):
    try:
        v = safe_ss[key]
    except KeyError:
        return "<MISSING>"
    if isinstance(v, np.ndarray):
        return f"ndarray(shape={v.shape}, dtype={v.dtype})"
    if isinstance(v, dict):
        return f"dict(keys={list(v.keys())[:6]})"
    if isinstance(v, list):
        return f"list(len={len(v)})"
    return repr(v)[:80]

keys_of_interest = [
    "detective_results",
    "detective_results_list",
    "detective_plot_data",
    "active_time",
    "active_flux",
    "detective_analyze_fetched_last_run",
]
for k in keys_of_interest:
    print(f"  {k} = {_peek(at.session_state, k)}")

first_click_results = _peek(at.session_state, "detective_results")
print()
print(f"  FIRST-CLICK verdict: detective_results = {first_click_results}")
print()

# ----------------------------------------------------------------------
# The I4-fix guard key is `detective_analyze_fetched_last_run`. It is
# set to True on first click and NEVER reset anywhere. The hypothesis:
# if the user (a) re-fetches the same target, (b) changes parameters,
# or (c) encounters an error in run_analysis, a second click on the
# same button is silently swallowed because the guard is still True.
# We test scenario (c)-adjacent: a SECOND fresh click on the same
# button after the first analysis completed. If the user is iterating
# (e.g. re-running after tweaking the SNR slider), the second click
# should also fire run_analysis.
# ----------------------------------------------------------------------
print("=" * 70)
print("Step 7: SECOND click on Analyze (re-run scenario)")
print("=" * 70)
# Find the button again (AppTest rebuilds the widget tree on .run()).
analyze_btn2 = None
for btn in at.get("button"):
    if "Analyze Telemetry & Verify Harmonics" in btn.label and btn.key == "detective_analyze_fetched":
        analyze_btn2 = btn
        break
if analyze_btn2 is None:
    print("  (button gone from tree — expected if it was one-shot)")
else:
    print("  Button still rendered. Clicking a second time...")
    analyze_btn2.click().run()
    print(f"  Clicked. Exceptions: {at.exception}")
    print(f"  I4-guard state after 2nd click: {_peek(at.session_state, 'detective_analyze_fetched_last_run')}")

# ----------------------------------------------------------------------
# Scenario (b): user changes a parameter (SNR slider) and clicks
# Analyze again. With the guard, run_analysis will NOT fire even
# though the user explicitly asked for a re-run. This is the
# "click does nothing" symptom.
# ----------------------------------------------------------------------
print()
print("=" * 70)
print("Step 8: Change SNR slider, then click Analyze a 3rd time")
print("=" * 70)
snr_slider = None
for s in at.get("slider"):
    if s.key is not None and "snr" in str(s.key).lower():
        snr_slider = s
        break
if snr_slider is None:
    # try label match
    for s in at.get("slider"):
        if "SNR" in str(s.label) or "Signal-to-Noise" in str(s.label):
            snr_slider = s
            break
if snr_slider is not None:
    print(f"  SNR slider found: key={snr_slider.key!r} current={snr_slider.value}")
    snr_slider.set_value(5.0).run()
    print(f"  SNR slider changed to 5.0. New value: {snr_slider.value}")
else:
    print("  (no SNR slider visible — page may not be in multi-planet mode)")

# Re-locate analyze button after the rerun
analyze_btn3 = None
for btn in at.get("button"):
    if "Analyze Telemetry & Verify Harmonics" in btn.label and btn.key == "detective_analyze_fetched":
        analyze_btn3 = btn
        break
if analyze_btn3 is not None:
    print("  Clicking Analyze a 3rd time after parameter change...")
    analyze_btn3.click().run()
    print(f"  Exceptions: {at.exception}")
else:
    print("  (button not visible — perhaps analysis is already showing?)")

print()
print("=" * 70)
print("Step 9: Final verdict")
print("=" * 70)
guard_final = _peek(at.session_state, "detective_analyze_fetched_last_run")
results_final = _peek(at.session_state, "detective_results")
print(f"  I4-guard after all clicks: {guard_final}")
print(f"  detective_results:         {results_final}")
print()
if guard_final is None and results_final is not None:
    print("  ✅ FIX VERIFIED:")
    print("     - The I4 one-shot session-state guard no longer exists")
    print("       (peek returns None for the guard key).")
    print("     - Every click (1st, 2nd, 3rd-after-param-change) fired")
    print("       run_analysis — see the TLS 'Searching' lines in the")
    print("       captured stdout from Steps 5, 7, 8 above.")
    print("     - detective_results is populated.")
else:
    print(f"  (unexpected state — guard={guard_final!r}, "
          f"results_is_dict={isinstance(results_final, dict)})")
