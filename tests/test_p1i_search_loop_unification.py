"""P1-I: search-loop unification (PRD v4.1 §2.5).

Before this bucket, ``_subprocess_search_worker`` (the async path used by
``submit_multi_planet_search``) was a *second copy* of the multi-planet
loop, and the two had drifted: GUARDRAIL 1 retried marginal candidates with
subtraction on the async path while breaking immediately on the sync path,
and both carried their own copy of the fail-closed TLS gate.  Two copies of
a load-bearing scientific guardrail is exactly how a bypass silently
reappears on one path and not the other.

These tests pin the retirement of that drift:

* the async worker is now an *adapter* -- it delegates to the one
  implementation and no longer carries its own guardrail copy;
* the two paths agree on a real injected curve.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path
from queue import Empty as _queue_Empty

import numpy as np
import pytest

from astraeus.core import orchestrator as orch
from astraeus.core.orchestrator import (
    JobState,
    _subprocess_search_worker,
    get_job_status,
    run_multi_planet_search,
    submit_multi_planet_search,
)

_ORCH = Path(orch.__file__).read_text(encoding="utf-8")


def _worker_source(*, strip_docstring: bool = True) -> str:
    """The source of ``_subprocess_search_worker`` only.

    With ``strip_docstring`` the docstring is excluded, so a docstring that
    *explains* the retired guardrail is not mistaken for the guardrail
    itself.
    """
    tree = ast.parse(_ORCH)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_subprocess_search_worker":
            if not strip_docstring:
                return ast.get_source_segment(_ORCH, node) or ""
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            return "\n".join(ast.unparse(stmt) for stmt in body)
    return ""


# -- the adapter contract -------------------------------------------------


def test_async_worker_is_an_adapter_not_a_copy():
    """The async worker must delegate rather than reimplement.

    A duplicated guardrail is the failure mode this bucket exists to close;
    if the loop body is re-inlined here, this test fails before the drift
    can silently re-diverge.
    """
    body = _worker_source()
    assert body, "_subprocess_search_worker not found in orchestrator.py"

    # It delegates to the single implementation...
    assert "run_multi_planet_search (" in body or "run_multi_planet_search(" in body, (
        "the async worker must call run_multi_planet_search rather than "
        "reimplement the loop (P1-I)"
    )
    # ...and carries no guardrail copy of its own.
    for marker in ("GUARDRAIL 1", "GUARDRAIL 2", "guardrail1_consecutive_marginal"):
        assert marker not in body, (
            f"_subprocess_search_worker must not carry its own copy of {marker}; "
            "the sync loop is the single implementation (P1-I)"
        )
    # The fail-closed gate likewise lives in one place.
    assert "ENV_UNAVAILABLE" not in body, (
        "the async worker must not re-implement the fail-closed TLS gate"
    )


def test_daemon_constraint_is_unchanged():
    """P1-I must not disturb the nested-pool contract the daemon pin
    protects (``tests/characterize/test_tls_call_path_contract.py``)."""
    tree = ast.parse(_ORCH)
    submit = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "submit_multi_planet_search"
    )
    ctors = [
        n
        for n in ast.walk(submit)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "Process"
    ]
    assert ctors, "submit_multi_planet_search must construct a Process"
    kwargs = {kw.arg: kw.value for kw in ctors[0].keywords}
    assert kwargs.get("daemon") and isinstance(kwargs["daemon"], ast.Constant)
    assert kwargs["daemon"].value is True


# -- the two paths agree --------------------------------------------------


def _injected_curve(period=12.345, seed=3, n=900):
    """A clear single transit: strong enough that both paths must accept it
    on the first iteration (so the test stays in the fast gate)."""
    rng = np.random.default_rng(seed)
    time = np.arange(0.0, n * 0.05, 0.05)
    epoch, dur, depth = 5.0, 0.12, 0.02
    flux = np.ones_like(time)
    ph = np.mod(time - epoch, period)
    flux[(ph < dur / 2) | (ph > period - dur / 2)] -= depth
    flux += rng.normal(0, 0.002, time.size)
    return {
        "time": time,
        "flux": flux,
        "target_name": "P1I-PARITY",
        "data_source": "synthetic",
        "metadata": {},
    }


@pytest.mark.smoke
def test_sync_and_async_paths_agree_on_an_injected_signal():
    """The unification's payoff: both paths find the same planet.

    A drift between the loops would show up here as a different accepted
    period (or a different candidate count) for identical input.
    """
    curve = _injected_curve()

    sync = run_multi_planet_search(curve, max_signals=1, snr_floor=7.0)
    assert len(sync) >= 1, "sync path must accept the injected candidate"
    sync_period = float(sync[0]["period"])

    job_id = submit_multi_planet_search(curve, max_signals=1, snr_floor=7.0)
    deadline = time.time() + 240
    status = None
    while time.time() < deadline:
        status = get_job_status(job_id)
        if status["status"] in (JobState.DONE, JobState.FAILED, JobState.CANCELLED):
            break
        time.sleep(0.5)

    assert status is not None and status["status"] == JobState.DONE, (
        f"async path must complete cleanly, got {status and status['status']} "
        f"(error={status and status.get('error')})"
    )
    async_candidates = status["candidates"]
    assert len(async_candidates) == len(sync), (
        f"path divergence: sync accepted {len(sync)}, async accepted "
        f"{len(async_candidates)} (P1-I unification)"
    )
    async_period = float(async_candidates[0]["period"])
    assert abs(async_period - sync_period) / sync_period < 0.01, (
        f"path divergence: sync period {sync_period:.4f}d vs async "
        f"{async_period:.4f}d exceeds 1%"
    )


def test_async_worker_reports_iterations():
    """The adapter must still forward *measured* progress (PRD §5.1)."""
    import multiprocessing

    curve = _injected_curve()
    q: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_subprocess_search_worker,
        args=(q, curve, 1, 7.0),
        daemon=True,
    )
    proc.start()
    types = []
    try:
        # The first TLS call dominates (~9-60 s on these curves, P05-A), so
        # poll patiently rather than assuming a stalled queue.
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                msg = q.get(timeout=10)
            except _queue_Empty:
                if not proc.is_alive():
                    break
                continue
            types.append(msg.get("type"))
            if msg.get("type") in ("done", "error"):
                break
    finally:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)

    assert "running" in types, "the adapter must announce start"
    assert types[-1] == "done", f"expected clean done, got trail {types}"
    assert "iteration" in types, "the adapter must forward measured progress"
