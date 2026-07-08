"""Regression test for the round-8 vetting-override bypass.

Contract locked by this test (R8):
  When detect_transit_candidate sets is_candidate=False because the
  TLS gate failed (tls_valid is False), the final vetting_status
  returned to the orchestrator must NOT start with "Verified Planet
  Candidate". The orchestrator's GUARDRAIL 1 reads
  vetting_status.startswith("Verified Planet Candidate") to decide
  whether to accept and continue iterating, so any string starting
  with that prefix bypasses the TLS gate.

This test does NOT prescribe the exact string the override should
produce (could be "rejected", "TLS Rejected", "Likely Planet",
etc., as long as it does NOT start with "Verified Planet Candidate");
that decision is the round-8 fix's design call. It just locks the
invariant: TLS-rejected candidates cannot be tagged as Verified.

Origin: round 7 J7c real-curve gate. Iter 1 of the orchestrator-style
loop found P=489.13d at SNR=16.37, dur=0.1d. TLS correctly rejected
it (tls_sde=4.22 < 5.0, tls_valid=False). VettingEngine then set
vetting_status='Verified Planet Candidate (Likely Planet)' via
detection.py:328-329. The orchestrator's string-prefix check
accepted that and subtracted the spurious signal, consuming an
iteration slot that would otherwise have gone to finding Kepler-90d.

R8 root cause: the orchestrator's accept path and the production
emission gate read different signals (vetting_status vs. is_candidate)
that can disagree when the VettingEngine overrides the default
vetting_status. The fix is at the orchestrator level (GUARDRAIL 1
must also check tls_valid) or at the classifier level (VettingEngine
must not set "Verified Planet Candidate*" when tls_valid is False).
The latter preserves the load-bearing TLS gate at the classifier,
the former is defense-in-depth at the orchestrator. Either fix
satisfies this regression test.
"""
from __future__ import annotations

from unittest import mock

import numpy as np
import pytest

# KNOWN FAILURE: this test locks the round-8 vetting-override bypass
# (see scratch/r8_repro_vetting_override.py + the round-7 J7c log).
# Marked xfail so CI doesn't fail while the round-8 fix is pending.
# When the fix lands, remove this xfail decorator and the test will
# turn green to confirm the bypass is closed.
pytestmark = pytest.mark.xfail(
    reason="Round 8: VettingEngine override at detection.py:328-329 sets "
           "'Verified Planet Candidate' on TLS-rejected candidates; the "
           "orchestrator's string-prefix check accepts that. Locked here "
           "so the fix turns this green.",
    strict=False,
)


def _force_tls_low_sde(*args, **kwargs):
    """Return a TLS .power() result object that fails the SDE >= 5.0 gate."""
    class _R:
        SDE = 4.0  # below the 5.0 threshold — same shape as J7c iter 1
        period = kwargs.get("period_max", 10.0) * 0.5 + kwargs.get("period_min", 5.0) * 0.5
        FAP = 0.5
    return _R()


def test_tls_rejected_candidate_cannot_be_tagged_verified() -> None:
    """The contract: when TLS rejects, vetting_status must not start with
    'Verified Planet Candidate'. Otherwise the orchestrator's string-
    prefix check accepts and bypasses the load-bearing TLS gate.

    KNOWN FAILURE (round 8): this test currently FAILS because the
    VettingEngine override at detection.py:328-329 sets
    vetting_status='Verified Planet Candidate (Likely Planet)' for
    geometric-vet-cleared candidates regardless of tls_valid. The
    orchestrator's GUARDRAIL 1 string-prefix check (orchestrator.py:
    168-170) accepts that, bypassing the load-bearing TLS gate that
    round-3's J2c nested-pool fix specifically built to stop
    confidently-wrong candidates. The round-8 fix will turn this
    green; do not remove the @pytest.mark.xfail decorator until then.
    See scratch/r8_repro_vetting_override.py for the minimal repro
    and the round-7 J7c log for the real-curve evidence.
    """
    # Build a minimal synthetic curve with one planet (same shape as
    # the round-7 J7c run; TLS will be mocked to fail, so the only
    # thing that matters is what vetting_status comes out as).
    rng = np.random.default_rng(seed=20260708)
    t = np.linspace(0, 200.0, 5000)
    flux = 1.0 + 1e-4 * rng.standard_normal(5000)
    period = 10.0
    dur = 0.1
    depth = 1e-3
    t0 = 5.0
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    flux[np.abs(phase) < dur / 2.0] -= depth

    # Force TLS to return SDE=4.0 (fails the >= 5.0 gate). Detect_transit_
    # candidate's import of transitleastsquares is local; we patch the
    # class so the .power() call on the model instance returns our low SDE.
    import transitleastsquares as tls_mod
    with mock.patch.object(tls_mod.transitleastsquares, "power",
                            side_effect=_force_tls_low_sde):
        from astraeus.analysis.detection import detect_transit_candidate
        result = detect_transit_candidate(
            time=t, flux=flux,
            target_name="R8-regression-test",
            data_source="synthetic",
            snr_threshold=7.1,
        )

    # The load-bearing TLS gate is the production emission gate at
    # detection.py:164-168. With tls_valid=False, is_candidate must be
    # False. If it isn't, that's a separate bug — the gate itself is
    # broken — but the regression we lock here is the contract between
    # the gate and the orchestrator's read of the result.
    assert result.get("tls_valid") is False, (
        "Test setup error: TLS should have been mocked to fail. "
        f"Got tls_valid={result.get('tls_valid')!r}"
    )
    assert result.get("is_candidate") is False, (
        "Test setup error: emission gate should reject a TLS-failed "
        f"candidate. Got is_candidate={result.get('is_candidate')!r}"
    )

    # THE REGRESSION: the orchestrator reads vetting_status with
    # .startswith('Verified Planet Candidate'). If the VettingEngine
    # override sets that string on a TLS-rejected candidate, the
    # orchestrator accepts it and the TLS gate is bypassed.
    vetting = result.get("vetting_status", "")
    assert not (isinstance(vetting, str)
                and vetting.startswith("Verified Planet Candidate")), (
        f"REGRESSION: TLS-rejected candidate tagged as "
        f"vetting_status={vetting!r}. The orchestrator's GUARDRAIL 1 "
        "string-prefix check would accept this candidate and bypass "
        "the load-bearing TLS gate. See round-7 J7c iter 1 (489.13d "
        "spurious peak, tls_sde=4.22, vetting='Verified Planet "
        "Candidate (Likely Planet)') for the failure case this locks."
    )
