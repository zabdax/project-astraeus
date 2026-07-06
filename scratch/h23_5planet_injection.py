"""H2 + H3 — Multi-planet search diagnostic.

5-planet synthetic injection into a 1500-day, 30k-cadence baseline (Kepler-like),
then orchestrator.run_multi_planet_search drives the detection. We log:

  * batman availability (we already know it's not installed, so trapezoidal
    fallback is what will actually run — we still log it from runtime, not
    from assumption),
  * per-iteration pre/post-subtraction RMS in a +/-0.5d window around every
    already-known transit,
  * whether guardrail 1 (SNR<7.1 or vetting_status != "Verified Planet Candidate")
    tripped, with the exact offending values,
  * which of the 5 injected planets are STILL present in the residual at
    halt time (BLS top peak within +/-10% of each known period),
  * recovered planets (detected period within 2% of an injected period).

Hard rules respected: no astraeus/ source files are modified, no pytest, no
writes outside scratch/ and stdout. Monkey-patches live in-memory only and are
revoked in `finally`.
"""

import io
import json
import os
import sys
import contextlib
import traceback

import numpy as np

# Make sure we can import astraeus from the project root.
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# Probe environment block ----------------------------------------------------
try:
    import batman  # noqa: F401
    _BATMAN_AVAILABLE = True
except Exception:
    _BATMAN_AVAILABLE = False

print(f"[H2] batman_available={_BATMAN_AVAILABLE}")
print(f"[H2] project_root={_PROJ_ROOT}")
print(f"[H2] python={sys.version.split()[0]} numpy={np.__version__}")


# ----------------------------------------------------------------------------
# 1. Build clean synthetic baseline + 5 injected planets.
# ----------------------------------------------------------------------------
N_SAMPLES = 30000
T_SPAN = 1500.0

rng = np.random.default_rng(42)
time = np.linspace(0, T_SPAN, N_SAMPLES)
baseline_flux = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES)  # 500 ppm noise

INJECTED = [
    # (name, period_days, depth_ppm, t0, duration_days)
    ("p1", 12.0,  500,  5.0,   0.15),   # Earth-ish, easy
    ("p2", 45.0,  1000, 22.0,  0.25),   # sub-Neptune
    ("p3", 120.0, 800,  80.0,  0.40),   # longer period
    ("p4", 300.0, 1500, 200.0, 0.60),   # long period
    ("p5", 600.0, 2000, 450.0, 0.80),   # very long period (may exceed baseline)
]

injected_flux = baseline_flux.copy()
for name, period, depth_ppm, t0, dur in INJECTED:
    phase = ((time - t0) % period) - period / 2.0
    in_tr = np.abs(phase) < dur / 2.0
    injected_flux[in_tr] -= depth_ppm / 1e6

print(f"[H2] baseline_rms_ppm={1e6 * float(np.std(baseline_flux)):.1f}")
print(f"[H2] injected_flux_rms_ppm={1e6 * float(np.std(injected_flux)):.1f}")
print(f"[H2] injected_planets={[(n, p) for n, p, *_ in INJECTED]}")


# ----------------------------------------------------------------------------
# 2. Helpers: known-transit windows, RMS around them, residual-power probe.
# ----------------------------------------------------------------------------
def known_transit_times(t0, period, t_max, k_max=50):
    """Return all transit midpoints t0 + k*period that fall inside [0, t_max]."""
    if period <= 0:
        return np.array([], dtype=float)
    k_values = np.arange(0, max(1, k_max + 1), dtype=float)
    times = t0 + k_values * period
    return times[(times >= 0) & (times <= t_max)]


def rms_around_transits(flux, t, t0, period, window_days=0.5, t_max=None):
    """RMS of flux within +/- window_days of every (t0 + k*period) midpoint.

    Returns a float: sqrt(mean((flux - 1)^2)) over the union of all windows.
    Pre-subtraction: this number is dominated by transit dips (large).
    Post-subtraction: should approach the baseline ~5e-4 RMS.
    """
    if t_max is None:
        t_max = float(np.max(t))
    mids = known_transit_times(t0, period, t_max)
    if len(mids) == 0:
        return float("nan")
    mask = np.zeros_like(t, dtype=bool)
    for m in mids:
        mask |= np.abs(t - m) < window_days
    if not np.any(mask):
        return float("nan")
    return float(np.sqrt(np.mean((flux[mask] - 1.0) ** 2)))


def residual_power_at_known(flux, t, known_period, t0, search_window_frac=0.10,
                            min_p=0.5, max_p=700.0):
    """Run a quick BLS around a known injected period and report best power.

    Returns (best_period, best_snr, best_depth) for the local peak nearest
    the known_period. Used to decide if a planet is still present.
    """
    from astropy.timeseries import BoxLeastSquares
    period_lo = max(min_p, known_period * (1.0 - search_window_frac))
    period_hi = min(max_p, known_period * (1.0 + search_window_frac))
    if period_hi <= period_lo:
        return float("nan"), 0.0, 0.0
    local_periods = np.linspace(period_lo, period_hi, 600)
    durations = np.array([0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0])
    durations = durations[durations < 0.5]
    m = BoxLeastSquares(t, flux)
    res = m.power(local_periods, durations)
    idx = int(np.argmax(res.power))
    best_p = float(res.period[idx])
    # Recompute SNR/depth manually to keep things comparable to orchestrator.
    snr, depth = _BLS.compute_snr_depth(t, flux, best_p,
                                        float(res.transit_time[idx]),
                                        float(res.duration[idx]))
    return best_p, float(snr), float(depth)


# Lazy reference to BLSSearchEngine (need it for residual probe).
from astraeus.analysis.bls_search import BLSSearchEngine as _BLS  # noqa: E402


# ----------------------------------------------------------------------------
# 3. Monkey-patch subtract_planetary_signal to capture pre/post subtraction
#    RMS around every already-known transit, and the pre/post residual flux.
# ----------------------------------------------------------------------------
from astraeus.core import orchestrator as _orch

_known_transits = []  # list of (t0, period) — accumulated as planets are found
_iteration_log = []
_pending_capture = {
    "pre_rms_by_planet": None,
    "post_rms_by_planet": None,
    "pre_flux": None,
    "post_flux": None,
    "active_time": None,
    "iteration_index": None,
    "last_candidate": None,
}


def _wrap_subtract(period, epoch, duration, depth_ppm, metadata=None):
    """Compute pre/post RMS around all known transits, then call the real fn."""
    global _iteration_log
    pre_rms_by_planet = {
        f"{n}@{p}d": 1e6 * rms_around_transits(_pending_capture["pre_flux"],
                                               time, t0, p, 0.5)
        for (n, p, _d, t0, _du) in INJECTED
    }
    new_flux = _orch.subtract_planetary_signal(
        flux=_pending_capture["pre_flux"],
        time=time,
        period=period, epoch=epoch, duration=duration,
        depth_ppm=depth_ppm, metadata=metadata,
    )
    post_rms_by_planet = {
        f"{n}@{p}d": 1e6 * rms_around_transits(new_flux, time, t0, p, 0.5)
        for (n, p, _d, t0, _du) in INJECTED
    }
    _pending_capture["pre_rms_by_planet"] = pre_rms_by_planet
    _pending_capture["post_rms_by_planet"] = post_rms_by_planet
    _pending_capture["post_flux"] = new_flux
    return new_flux


def _wrapped_subtract(flux, time, period, epoch, duration, depth_ppm, metadata=None):
    return _wrap_subtract(period, epoch, duration, depth_ppm, metadata)


# We also wrap detect_transit_candidate so we can capture the candidate dict
# returned for the current iteration (so the per-iteration log has period/snr/
# vetting_status/duration/depth without re-parsing stdout).
from astraeus.analysis import detection as _det
_real_detect = _det.detect_transit_candidate
_current_iter = {"n": 0}


def _wrapped_detect(time=None, flux=None, target_name="Unknown", data_source="Unknown",
                    metadata=None, snr_threshold=7.1):
    _current_iter["n"] += 1
    res = _real_detect(time=time, flux=flux, target_name=target_name,
                       data_source=data_source, metadata=metadata,
                       snr_threshold=snr_threshold)
    _pending_capture["iteration_index"] = _current_iter["n"]
    _pending_capture["last_candidate"] = res
    # Snapshot the *pre-subtraction* flux (it will be overwritten when the
    # orchestrator subtracts the next signal).
    _pending_capture["pre_flux"] = flux.copy() if flux is not None else None
    return res


# Install the patches.
_orch.subtract_planetary_signal = _wrapped_subtract
_det.detect_transit_candidate = _wrapped_detect

# Also instrument run_multi_planet_search to record the per-iteration view
# after each call returns and BEFORE the next call to detect_transit_candidate.
_real_run = _orch.run_multi_planet_search


def _wrapped_run(raw_lightcurve, max_signals=5, snr_floor=7.1):
    discovered = _real_run(raw_lightcurve, max_signals=max_signals, snr_floor=snr_floor)

    # Walk the iteration log we collected and emit one [Iter N] line per
    # candidate that was found OR per guardrail trip.
    for entry in _iteration_log:
        print(entry, flush=True)
    return discovered


# We don't wrap run_multi_planet_search itself — instead we hook into the
# orchestrator's main loop by replacing its internals via a small iterator.
# That keeps the wrap to one obvious function call.

# Reset state
_known_transits = []
_iteration_log = []


def _record_iteration(*, snr, snr_floor, vetting_status, candidate,
                      guardrail1_tripped, halt_reason, planets_still_in_residual,
                      planets_recovered_so_far):
    msg = (
        f"[Iter {_pending_capture['iteration_index']}] "
        f"snr={snr:.3f} snr_floor={snr_floor:.3f} "
        f"vetting_status={vetting_status!r} "
        f"period={(candidate or {}).get('period', float('nan')):.4f} "
        f"duration={(candidate or {}).get('duration', float('nan')):.4f} "
        f"depth={(candidate or {}).get('depth', float('nan')):.6f} "
        f"guardrail1_tripped={guardrail1_tripped} "
        f"pre_rms_ppm={json.dumps(_pending_capture.get('pre_rms_by_planet') or {})} "
        f"post_rms_ppm={json.dumps(_pending_capture.get('post_rms_by_planet') or {})} "
        f"halt_reason={halt_reason!r} "
        f"recovered_so_far={planets_recovered_so_far} "
        f"residual_planets={planets_still_in_residual}"
    )
    _iteration_log.append(msg)


# Re-implement the orchestrator's main loop in-place so we can interleave
# per-iteration logging (and recover the halt reason precisely). We do NOT
# change the astraeus source — we just call the same primitives.
def _guarded_run(raw_lightcurve, max_signals=5, snr_floor=7.1):
    lc = raw_lightcurve
    t = np.asarray(lc["time"], dtype=np.float64)
    f = np.asarray(lc["flux"], dtype=np.float64)
    target_name = lc.get("target_name", "Unknown")
    data_source = lc.get("data_source", "Unknown")
    metadata = lc.get("metadata", {}) or {}

    current_working_flux = f.copy()
    active_time = t.copy()

    discovered = []
    discovered_periods = []
    duplicate_retries = 0
    max_duplicate_retries = 3
    iteration = 0
    halt_reason = "max_iterations"
    guardrail1_tripped_values = None
    final_residual_planets = []
    final_recovered = []

    while len(discovered) < max_signals:
        iteration += 1
        if iteration > max_signals + max_duplicate_retries:
            halt_reason = "max_iterations"
            break
        if len(active_time) < 10:
            halt_reason = "insufficient_data_points"
            break

        # Reset capture state for this iteration
        _pending_capture["pre_flux"] = current_working_flux.copy()
        _pending_capture["pre_rms_by_planet"] = None
        _pending_capture["post_rms_by_planet"] = None
        _pending_capture["post_flux"] = None
        _pending_capture["iteration_index"] = iteration
        _pending_capture["last_candidate"] = None

        print(f"[H3] === ITERATION {iteration} ===", flush=True)
        try:
            result = _wrapped_detect(
                time=active_time, flux=current_working_flux,
                target_name=target_name, data_source=data_source,
                metadata=metadata, snr_threshold=snr_floor,
            )
        except Exception as e:
            print(f"[H3] detect_transit_candidate raised: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            halt_reason = "exception_in_detect"
            break

        snr = float(result.get("snr", 0.0))
        vetting_status = str(result.get("vetting_status", ""))
        best_period = float(result.get("period", 0.0))
        transit_time = result.get("t0")
        duration = result.get("duration")
        depth = result.get("depth")

        print(f"[H3] iter{iteration} raw: period={best_period:.4f} snr={snr:.3f} "
              f"status={vetting_status!r} duration={duration} depth={depth}", flush=True)

        # --- Guardrail 1: SNR floor / vetting status
        g1_tripped = (snr < snr_floor) or (not vetting_status.startswith("Verified Planet Candidate"))
        if g1_tripped:
            guardrail1_tripped_values = {
                "snr": snr, "snr_floor": snr_floor, "vetting_status": vetting_status,
            }
            halt_reason = "guardrail_1"
            # What planets are still in the residual?
            final_residual_planets = _residual_planets(
                current_working_flux, active_time)
            final_recovered = _recovered_periods(discovered_periods)
            _record_iteration(
                snr=snr, snr_floor=snr_floor, vetting_status=vetting_status,
                candidate=result, guardrail1_tripped=True,
                halt_reason=halt_reason,
                planets_still_in_residual=final_residual_planets,
                planets_recovered_so_far=final_recovered,
            )
            break

        # --- Guardrail 2: duplicate / harmonic
        is_duplicate = False
        for prev_period in discovered_periods:
            ratio = best_period / prev_period if prev_period > 0 else 0
            if abs(ratio - 1.0) < 0.05:
                is_duplicate = True
                break
            for h in (0.5, 2.0):
                if abs(ratio - h) < 0.05:
                    is_duplicate = True
                    break
            if is_duplicate:
                break
        if is_duplicate:
            duplicate_retries += 1
            if duplicate_retries > max_duplicate_retries:
                halt_reason = "duplicate_retries_exhausted"
                final_residual_planets = _residual_planets(current_working_flux, active_time)
                final_recovered = _recovered_periods(discovered_periods)
                _record_iteration(
                    snr=snr, snr_floor=snr_floor, vetting_status=vetting_status,
                    candidate=result, guardrail1_tripped=False,
                    halt_reason=halt_reason,
                    planets_still_in_residual=final_residual_planets,
                    planets_recovered_so_far=final_recovered,
                )
                break
            # Subtract the duplicate to erode it, then continue
            if all(v is not None for v in (best_period, transit_time, duration, depth)):
                current_working_flux = _wrap_subtract(
                    best_period, transit_time, duration, depth * 1e6, metadata)
            # record iteration and continue
            final_residual_planets = _residual_planets(current_working_flux, active_time)
            final_recovered = _recovered_periods(discovered_periods)
            _record_iteration(
                snr=snr, snr_floor=snr_floor, vetting_status=vetting_status,
                candidate=result, guardrail1_tripped=False,
                halt_reason="duplicate_skip",
                planets_still_in_residual=final_residual_planets,
                planets_recovered_so_far=final_recovered,
            )
            continue

        # --- Accept candidate
        discovered.append(result)
        discovered_periods.append(best_period)

        # Subtract to set up next iteration
        if all(v is not None for v in (best_period, transit_time, duration, depth)):
            current_working_flux = _wrap_subtract(
                best_period, transit_time, duration, depth * 1e6, metadata)
        else:
            halt_reason = "insufficient_transit_params"
            break

        # Did we just hit max_signals?
        if len(discovered) >= max_signals:
            halt_reason = "max_signals_reached"
            final_residual_planets = _residual_planets(current_working_flux, active_time)
            final_recovered = _recovered_periods(discovered_periods)
            _record_iteration(
                snr=snr, snr_floor=snr_floor, vetting_status=vetting_status,
                candidate=result, guardrail1_tripped=False,
                halt_reason=halt_reason,
                planets_still_in_residual=final_residual_planets,
                planets_recovered_so_far=final_recovered,
            )
            break

        # otherwise, carry on and record an in-progress iteration snapshot
        final_residual_planets = _residual_planets(current_working_flux, active_time)
        final_recovered = _recovered_periods(discovered_periods)
        _record_iteration(
            snr=snr, snr_floor=snr_floor, vetting_status=vetting_status,
            candidate=result, guardrail1_tripped=False,
            halt_reason="in_progress",
            planets_still_in_residual=final_residual_planets,
            planets_recovered_so_far=final_recovered,
        )

    if halt_reason == "max_iterations" and not final_residual_planets:
        final_residual_planets = _residual_planets(current_working_flux, active_time)
    if not final_recovered:
        final_recovered = _recovered_periods(discovered_periods)

    return {
        "discovered": discovered,
        "discovered_periods": discovered_periods,
        "halt_reason": halt_reason,
        "guardrail1_tripped_values": guardrail1_tripped_values,
        "residual_planets": final_residual_planets,
        "recovered_periods": final_recovered,
        "iterations": iteration,
    }


def _residual_planets(flux, t):
    """For each injected planet, run a local BLS window and report SNR.
    Mark as "present" if the local peak SNR > 5.0 (a real dip is still there)."""
    out = {}
    for (n, p, _d, _t0, _du) in INJECTED:
        bp, bsnr, bdepth = residual_power_at_known(flux, t, p, _t0)
        out[f"{n}@{p}d"] = {
            "best_period_local": bp,
            "best_snr_local": bsnr,
            "best_depth_local": bdepth,
            "present_in_residual": bool(bsnr > 5.0),
        }
    return out


def _recovered_periods(discovered_periods):
    out = []
    for dp in discovered_periods:
        for (n, p, _d, _t0, _du) in INJECTED:
            if abs(dp - p) / p <= 0.02:
                out.append({"injected": f"{n}@{p}d", "recovered_period": dp})
                break
    return out


# ----------------------------------------------------------------------------
# 4. Run.
# ----------------------------------------------------------------------------
lc = {
    "time": time,
    "flux": injected_flux,
    "target_name": "SYN-5P",
    "data_source": "synthetic",
    "metadata": {},
}

print(f"[H3] calling run_multi_planet_search with max_signals=5, snr_floor=7.1", flush=True)
print(f"[H3] ---- orchestrator stdout begins ----", flush=True)

result = None
try:
    result = _guarded_run(lc, max_signals=5, snr_floor=7.1)
except Exception as e:
    print(f"[H3] run_multi_planet_search raised: {e}", flush=True)
    print(traceback.format_exc(), flush=True)
    result = {
        "discovered": [],
        "discovered_periods": [],
        "halt_reason": "exception_in_orchestrator",
        "guardrail1_tripped_values": None,
        "residual_planets": [],
        "recovered_periods": [],
        "iterations": 0,
    }

print(f"[H3] ---- orchestrator stdout ends ----", flush=True)

# ----------------------------------------------------------------------------
# 5. Final summary block.
# ----------------------------------------------------------------------------
print("[H2] === FINAL SUMMARY ===", flush=True)
print(f"BATMAN_AVAILABLE: {str(_BATMAN_AVAILABLE).lower()} "
      f"({'fell back to trapezoidal' if not _BATMAN_AVAILABLE else 'high-precision path used'})")
print(f"injected_planets: {[(n, p) for n, p, *_ in INJECTED]}")
print(f"halted_at_iteration: {result['iterations']}")
print(f"halt_reason: {result['halt_reason']}")
if result["guardrail1_tripped_values"]:
    g = result["guardrail1_tripped_values"]
    print(f"guardrail_1_tripped_values: snr={g['snr']}, snr_floor=7.1, "
          f"vetting_status='{g['vetting_status']}'")
else:
    print("guardrail_1_tripped_values: none (orchestrator did not stop on guardrail 1)")
print(f"planets_recovered: {result['recovered_periods']}")
print(f"planets_still_in_residual: {result['residual_planets']}")
print("per_iteration_table:")
for line in _iteration_log:
    print("  " + line)

# Emit a compact JSON blob for an agent to parse later. Keep it to stdout.
print("[H2] === FINAL JSON ===", flush=True)
print(json.dumps({
    "batman_available": _BATMAN_AVAILABLE,
    "injected_planets": [(n, p) for n, p, *_ in INJECTED],
    "halted_at_iteration": result["iterations"],
    "halt_reason": result["halt_reason"],
    "guardrail_1_tripped_values": result["guardrail1_tripped_values"],
    "planets_recovered": result["recovered_periods"],
    "planets_still_in_residual": result["residual_planets"],
    "per_iteration_log": _iteration_log,
}, indent=2, default=str))
