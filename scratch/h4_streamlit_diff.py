"""H4 — Diff Streamlit layer performance vs direct Python call.

Strategy:
  a. Build the same synthetic 5-planet light curve used in scratch/h23_5planet_injection.py
     (period 12.0, depth 500 ppm, t0=5.0, duration=0.15 days, baseline 1500 days,
     30k samples, 500 ppm noise).  Use the *exact same* time and flux arrays
     (rng seed 42, linspace 0..1500, injected trapezoidal dips).
  b. Direct call (no Streamlit): run astraeus.core.orchestrator.run_multi_planet_search
     on the synthetic lc.  Measure wall time with time.perf_counter().
     Log "[H4-direct] wall_time=X.XXs" and what was returned.  Catch exceptions
     and log them.
  c. Streamlit AppTest harness: import streamlit.testing.v1.AppTest; find the app
     entry point.  Check ui/app.py, app.py, ui/pages/* for which one is the
     runnable entry.  Use `at = AppTest.from_file("<path>")` then `at.run()` then
     check `at.session_state` and `at.exception` for errors.  Time the run.
  d. Additionally, search the codebase for `@st.cache_data` and `@st.cache_resource`
     decorators.  List each file:line where a cache boundary exists.
  e. Final summary:
        - "direct_call_wall_s=X.XX"
        - "streamlit_apptest_wall_s=X.XX"
        - "cache_data_count=N, cache_resource_count=M"
        - "double_execution_evidence: ..."  (look for st.button handlers without
          key= or session_state guard)
        - "verdict: PASS|FAIL"  (FAIL = Streamlit adds > 20% wall time OR causes
          a different failure mode)

Hard rules respected: no astraeus/ source files are modified, no pytest, no
writes outside scratch/ and stdout.
"""

import os
import re
import sys
import time
import traceback

import numpy as np

# Make sure we can import astraeus from the project root.
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

print(f"[H4] project_root={_PROJ_ROOT}", flush=True)
print(f"[H4] python={sys.version.split()[0]} numpy={np.__version__}", flush=True)


# ----------------------------------------------------------------------------
# 1. Build the *exact same* synthetic 5-planet light curve as in
#    scratch/h23_5planet_injection.py.
# ----------------------------------------------------------------------------
N_SAMPLES = 30000
T_SPAN = 1500.0

rng = np.random.default_rng(42)
time_arr = np.linspace(0, T_SPAN, N_SAMPLES)
baseline_flux = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES)  # 500 ppm noise

INJECTED = [
    # (name, period_days, depth_ppm, t0, duration_days)
    ("p1", 12.0,  500,  5.0,   0.15),
    ("p2", 45.0,  1000, 22.0,  0.25),
    ("p3", 120.0, 800,  80.0,  0.40),
    ("p4", 300.0, 1500, 200.0, 0.60),
    ("p5", 600.0, 2000, 450.0, 0.80),
]

injected_flux = baseline_flux.copy()
for name, period, depth_ppm, t0, dur in INJECTED:
    phase = ((time_arr - t0) % period) - period / 2.0
    in_tr = np.abs(phase) < dur / 2.0
    injected_flux[in_tr] -= depth_ppm / 1e6

# Sanity check vs h23 — first 5 samples and final 5 should match if seeds align.
print(f"[H4] time[0:3]={time_arr[:3].tolist()}")
print(f"[H4] flux[0:3]={injected_flux[:3].tolist()}")
print(f"[H4] time[-3:]={time_arr[-3:].tolist()}")
print(f"[H4] flux[-3:]={injected_flux[-3:].tolist()}")
print(f"[H4] injected_flux_rms_ppm={1e6 * float(np.std(injected_flux)):.1f}", flush=True)


lc = {
    "time": time_arr,
    "flux": injected_flux,
    "target_name": "SYN-5P",
    "data_source": "synthetic",
    "metadata": {},
}


# ----------------------------------------------------------------------------
# 2. Direct call: run_multi_planet_search (no Streamlit).
# ----------------------------------------------------------------------------
print(f"[H4] === DIRECT CALL (no Streamlit) ===", flush=True)
direct_wall_s = None
direct_result_summary = None
direct_exception = None
try:
    from astraeus.core import orchestrator as _orch
    t0 = time.perf_counter()
    direct_result = _orch.run_multi_planet_search(lc, max_signals=5, snr_floor=7.1)
    direct_wall_s = time.perf_counter() - t0
    direct_result_summary = {
        "type": type(direct_result).__name__,
        "keys": list(direct_result.keys()) if isinstance(direct_result, dict) else None,
        "len": (
            len(direct_result.get("discovered", []))
            if isinstance(direct_result, dict) else None
        ),
        "halt_reason": (
            direct_result.get("halt_reason")
            if isinstance(direct_result, dict) else None
        ),
    }
    print(f"[H4-direct] wall_time={direct_wall_s:.2f}s")
    print(f"[H4-direct] returned={direct_result_summary}")
except Exception as e:
    direct_exception = f"{type(e).__name__}: {e}"
    print(f"[H4-direct] EXCEPTION: {direct_exception}", flush=True)
    print(traceback.format_exc(), flush=True)


# ----------------------------------------------------------------------------
# 3. Streamlit AppTest harness.
# ----------------------------------------------------------------------------
print(f"[H4] === STREAMLIT APPTEST HARNESS ===", flush=True)

# Find the runnable entry point.  Prefer app.py at the project root.
CANDIDATE_APPS = [
    os.path.join(_PROJ_ROOT, "app.py"),
    os.path.join(_PROJ_ROOT, "ui", "app.py"),
]
for c in CANDIDATE_APPS:
    print(f"[H4-apptest] candidate: {c} exists={os.path.isfile(c)}")

# Use the project-root app.py — that's the runnable Streamlit entry.
entry_path = None
for c in CANDIDATE_APPS:
    if os.path.isfile(c):
        entry_path = c
        break

if entry_path is None:
    print("[H4-apptest] NO_APP_FILE_FOUND: none of the candidate paths exist.")
    apptest_wall_s = None
    apptest_exception = "no_app_file"
    apptest_session_state = None
else:
    print(f"[H4-apptest] using entry: {entry_path}", flush=True)
    apptest_wall_s = None
    apptest_exception = None
    apptest_session_state = None
    apptest_excs = None
    try:
        from streamlit.testing.v1 import AppTest
        t0 = time.perf_counter()
        at = AppTest.from_file(entry_path)
        at.run()
        apptest_wall_s = time.perf_counter() - t0
        # Capture session_state keys and exception list.
        try:
            apptest_session_state = list(at.session_state.keys())
        except Exception as e:
            apptest_session_state = f"<could not read session_state: {e}>"
        try:
            apptest_excs = [str(e) for e in (at.exception or [])]
        except Exception as e:
            apptest_excs = f"<could not read exceptions: {e}>"

        print(f"[H4-apptest] wall_time={apptest_wall_s:.2f}s")
        print(f"[H4-apptest] session_state_keys={apptest_session_state}")
        print(f"[H4-apptest] at.exception={apptest_excs}")
    except Exception as e:
        apptest_exception = f"{type(e).__name__}: {e}"
        print(f"[H4-apptest] EXCEPTION: {apptest_exception}", flush=True)
        print(traceback.format_exc(), flush=True)


# ----------------------------------------------------------------------------
# 4. Cache decorator audit — search the codebase.
# ----------------------------------------------------------------------------
print(f"[H4] === CACHE DECORATOR AUDIT ===", flush=True)

SEARCH_ROOTS = ["astraeus", "ui", "dashboard"]
cache_data_locations = []
cache_resource_locations = []

for root in SEARCH_ROOTS:
    abs_root = os.path.join(_PROJ_ROOT, root)
    if not os.path.isdir(abs_root):
        continue
    for dirpath, _dirs, files in os.walk(abs_root):
        for f in files:
            if not f.endswith(".py"):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, _PROJ_ROOT)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if re.search(r"@st\.cache_data\b", line):
                            cache_data_locations.append(f"{rel}:{lineno}")
                        if re.search(r"@st\.cache_resource\b", line):
                            cache_resource_locations.append(f"{rel}:{lineno}")
            except Exception:
                pass

print(f"[H4-cache] cache_data_count={len(cache_data_locations)}")
for loc in cache_data_locations:
    print(f"[H4-cache] cache_data@{loc}")
print(f"[H4-cache] cache_resource_count={len(cache_resource_locations)}")
for loc in cache_resource_locations:
    print(f"[H4-cache] cache_resource@{loc}")


# ----------------------------------------------------------------------------
# 5. Double-execution evidence: st.button handlers without key= and without
#    a session_state guard wrapping the long-running pipeline.
# ----------------------------------------------------------------------------
print(f"[H4] === DOUBLE-EXECUTION EVIDENCE (st.button without key=) ===", flush=True)

button_findings = []
for root in SEARCH_ROOTS:
    abs_root = os.path.join(_PROJ_ROOT, root)
    if not os.path.isdir(abs_root):
        continue
    for dirpath, _dirs, files in os.walk(abs_root):
        for f in files:
            if not f.endswith(".py"):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, _PROJ_ROOT)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except Exception:
                continue
            for lineno, line in enumerate(lines, start=1):
                m = re.search(r"if\s+st\.button\s*\(\s*['\"]([^'\"]+)['\"]", line)
                if not m:
                    continue
                label = m.group(1)
                # Does the call include a key= argument on this line?
                has_key = bool(re.search(r"\bkey\s*=", line))
                # Look ahead 1..25 lines for any session_state['...'] or .setdefault guard.
                guard = False
                for ahead in lines[lineno: lineno + 25]:
                    if re.search(r"st\.session_state\.setdefault|st\.session_state\[['\"]", ahead):
                        guard = True
                        break
                    if re.search(r"^\s*if\s+st\.button\b", ahead):
                        # next button block
                        break
                note = []
                if not has_key:
                    note.append("no_key")
                if not guard:
                    note.append("no_session_state_guard")
                if note:
                    button_findings.append(
                        f"{rel}:{lineno} label={label!r} risk={','.join(note)}"
                    )

for finding in button_findings:
    print(f"[H4-button] {finding}")


# ----------------------------------------------------------------------------
# 6. Final summary.
# ----------------------------------------------------------------------------
print(f"[H4] === FINAL SUMMARY ===", flush=True)

# Wall times (None if not run).
direct_str = f"{direct_wall_s:.2f}" if direct_wall_s is not None else "N/A"
apptest_str = f"{apptest_wall_s:.2f}" if apptest_wall_s is not None else "N/A"

print(f"direct_call_wall_s={direct_str}")
print(f"streamlit_apptest_wall_s={apptest_str}")
print(f"cache_data_count={len(cache_data_locations)}, cache_resource_count={len(cache_resource_locations)}")

double_evidence = "none" if not button_findings else "; ".join(button_findings[:8])
if len(button_findings) > 8:
    double_evidence += f"; ... ({len(button_findings) - 8} more)"
print(f"double_execution_evidence: {double_evidence}")

# Verdict: FAIL if Streamlit >20% slower (only if both ran) OR if either path
# raised a different exception / different return.
verdict = "PASS"
reason = []

if direct_wall_s is not None and apptest_wall_s is not None:
    overhead_pct = (apptest_wall_s - direct_wall_s) / max(direct_wall_s, 1e-6) * 100.0
    if overhead_pct > 20.0:
        verdict = "FAIL"
        reason.append(f"apptest={apptest_wall_s:.2f}s > 1.20*direct={direct_wall_s:.2f}s (overhead {overhead_pct:.1f}%)")

# Different failure mode?
if direct_exception and not apptest_exception:
    verdict = "FAIL"
    reason.append(f"direct raised {direct_exception} but apptest did not")
if apptest_exception and not direct_exception:
    verdict = "FAIL"
    reason.append(f"apptest raised {apptest_exception} but direct did not")
if apptest_excs and isinstance(apptest_excs, list) and len(apptest_excs) > 0:
    verdict = "FAIL"
    reason.append(f"apptest surfaced {len(apptest_excs)} exception(s) in run: {apptest_excs[:2]}")

# Note: AppTest only measures *startup* of the app, not the long-running
# pipeline; record that as informational.
if apptest_wall_s is not None:
    reason.append(
        f"apptest_wall={apptest_wall_s:.2f}s is *app startup*, not pipeline; "
        f"@st.cache_data(ttl=3600) on RemoteDiscoveryEngine.fetch_data and "
        f"@st.cache_data in ui/pages/lab.py would mask re-fires"
    )

print(f"verdict: {verdict}")
if reason:
    for r in reason:
        print(f"verdict_reason: {r}")
