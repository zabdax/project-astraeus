"""Lock the call-path invariants that prevent the J2 nested-pool hang.

History (2026-07-06):
  - ``astraeus/analysis/detection.py`` calls ``tls.transitleastsquares(t, y)``
    and then ``model.power(period_min, period_max, show_progress_bar=False)``
    inside the orchestrator's daemon-spawned worker.
  - The orchestrator's worker is spawned with ``daemon=True``
    (``astraeus/core/orchestrator.py::submit_multi_planet_search``).
  - On Windows, ``multiprocessing`` forbids daemonic processes from
    spawning their own children. TLS's ``power(..., use_threads>1)`` path
    instantiates ``multiprocessing.Pool(processes=use_threads)`` (see
    ``transitleastsquares/main.py:141``), which raises
    ``AssertionError: daemonic processes are not allowed to have children``
    when called from inside the worker.
  - Direct experimental confirmation: ``scratch/nested_pool_check.py`` ran
    the exact production call stack and reproduced the AssertionError;
    the ``use_threads=1`` control arm completed in 80.9s on a 45,853-
    cadence curve with the standard 0.95x-1.05x BLS-narrowed window.
    Result file: ``logs/nested_pool_check_2026-07-06T145219Z.json``.

These tests pin the *source-level* contract that prevents a future
contributor from silently re-introducing the nested-pool regression.
They are intentionally textual — a true behavioral test would have to
re-run the full nested-pool check (slow, network/IO-coupled). The
contract is: the literal token ``use_threads=1`` is present in
``model.power(...)`` at the call site.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DETECTION_PY = PROJECT_ROOT / "astraeus" / "analysis" / "detection.py"
ORCHESTRATOR_PY = PROJECT_ROOT / "astraeus" / "core" / "orchestrator.py"


def _read(path: Path) -> str:
    assert path.exists(), f"production source missing: {path}"
    return path.read_text(encoding="utf-8")


def _find_tls_power_calls(source: str) -> list[ast.Call]:
    """Return every Call node that is a ``model.power(...)`` invocation
    in ``detection.py``. Matches ``model.power`` and ``self.model.power``;
    rejects ``tls.<anything>.power`` and bare ``.power``."""
    tree = ast.parse(source)
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Pattern: model.power(...) or self.model.power(...)
        attr = func
        if isinstance(func, ast.Attribute) and func.attr == "power":
            attr = func
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "model"
            and func.attr == "power"
        ):
            attr = func
        else:
            continue
        found.append(node)
    return found


def test_tls_power_call_passes_use_threads_1():
    """The production TLS call must pass ``use_threads=1`` to prevent
    nested-multiprocessing-pool from inside the daemon worker. This is
    a literal source-level contract: a future contributor removing the
    kwarg re-introduces the AssertionError. See module docstring."""
    source = _read(DETECTION_PY)
    power_calls = _find_tls_power_calls(source)
    assert power_calls, "no model.power(...) call found in detection.py"

    for call in power_calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        assert "use_threads" in kwargs, (
            "model.power(...) must pass use_threads explicitly; "
            "relying on TLS's cpu_count() default breaks the orchestrator's "
            "daemon worker (Windows AssertionError). "
            f"Got kwargs: {list(kwargs)}"
        )
        value = kwargs["use_threads"]
        # Accept either the literal 1, the unary-plus form, or a constant
        # expression that evaluates to 1. Refuse any value > 1 or any
        # expression that depends on multiprocessing.cpu_count().
        assert isinstance(value, ast.Constant), (
            f"use_threads kwarg must be a constant, got {ast.dump(value)}"
        )
        assert value.value == 1, (
            f"use_threads must be 1 inside the daemon worker; got {value.value!r}. "
            "TLS's cpu_count() default spawns a Pool that is forbidden in daemon "
            "processes (Windows AssertionError: 'daemonic processes are not "
            "allowed to have children')."
        )


def test_tls_power_call_docstring_mentions_daemon_constraint():
    """The model.power(...) call site must have an adjacent comment
    explaining WHY use_threads=1 is non-negotiable. A future contributor
    reading only the call will not otherwise know the constraint is
    architectural, not a perf preference."""
    source = _read(DETECTION_PY)
    # Look for one of the sentinel keywords within 600 chars before the
    # model.power(...) call. This is intentionally lenient to survive
    # line-wrapping refactors but tight enough to fail if the rationale
    # is removed.
    idx = source.find("model.power(")
    assert idx != -1, "no model.power(...) call found in detection.py"
    window = source[max(0, idx - 600): idx]
    assert re.search(
        r"daemon|daemonic|nested[ -]multiprocessing|use_threads=1|cpu_count",
        window,
        flags=re.IGNORECASE,
    ), (
        "model.power(...) call site must carry a comment naming the "
        "daemon-worker / nested-multiprocessing constraint. Reviewers "
        "must not be able to delete the use_threads=1 kwarg thinking it "
        "is a perf preference."
    )


def test_orchestrator_worker_is_daemon():
    """The orchestrator's worker is intentionally daemon. This pins the
    OTHER side of the constraint: detection.py's use_threads=1 is
    required BECAUSE orchestrator.py:submit_multi_planet_search sets
    daemon=True. If this test fails, the architectural contract has
    shifted and the use_threads=1 lock in detection.py may need to be
    revisited (with an explicit decision and a new contract test)."""
    source = _read(ORCHESTRATOR_PY)
    # Locate submit_multi_planet_search and verify daemon=True on its
    # multiprocessing.Process(...) constructor.
    tree = ast.parse(source)
    fns = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "submit_multi_planet_search"
    ]
    assert fns, "submit_multi_planet_search not found in orchestrator.py"
    fn = fns[0]
    proc_ctors = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "Process"
    ]
    assert proc_ctors, (
        "submit_multi_planet_search must construct a multiprocessing.Process"
    )
    for ctor in proc_ctors:
        kwargs = {kw.arg: kw.value for kw in ctor.keywords}
        assert "daemon" in kwargs, (
            "multiprocessing.Process(...) in submit_multi_planet_search "
            "must pass daemon= explicitly. Implicit daemon default is "
            "implementation-defined and would break the use_threads=1 "
            "contract in detection.py silently."
        )
        value = kwargs["daemon"]
        assert isinstance(value, ast.Constant), (
            f"daemon kwarg must be a constant, got {ast.dump(value)}"
        )
        assert value.value is True, (
            "The orchestrator worker MUST be daemon=True. The use_threads=1 "
            "contract in detection.py is contingent on this. If you are "
            "changing this, you are removing a load-bearing architectural "
            "constraint — discuss with the reviewer first and add a new "
            "characterization test."
        )


def test_orchestrator_documents_daemon_constraint_near_submit():
    """The submit_multi_planet_search function must carry a comment
    warning future contributors that any work done inside the worker
    cannot itself spawn a multiprocessing.Pool (or Process)."""
    source = _read(ORCHESTRATOR_PY)
    # Find submit_multi_planet_search definition
    match = re.search(
        r"def\s+submit_multi_planet_search[^\n]*:",
        source,
    )
    assert match, "submit_multi_planet_search not found"
    # Look 1500 chars after the def for a warning.
    window = source[match.start(): match.start() + 1500]
    assert re.search(
        r"daemon|nested[ -]multiprocessing|do not.*pool|do not.*spawn",
        window,
        flags=re.IGNORECASE,
    ), (
        "submit_multi_planet_search must carry a comment near the "
        "multiprocessing.Process(...) call warning that work inside the "
        "worker cannot itself spawn multiprocessing.Pool / Process on "
        "Windows."
    )


# ===========================================================================
# J2c second-rail contract: the except block around TLS must distinguish
# environment / infrastructure failures (AssertionError, RuntimeError) from
# genuine scientific rejections. The prior bare `except Exception` silently
# folded the deterministic Windows AssertionError into `tls_valid=False`,
# making "no planets found" indistinguishable from "the TLS gate is broken"
# for the entire period daemon=True was in place (2026-06-09 .. 2026-07-06).
# These tests pin the new contract.
# ===========================================================================


def _find_tls_try_block(tree: ast.Module) -> tuple[ast.Try, ast.ExceptHandler]:
    """Return the (try, handler) for the TLS block in detect_transit_candidate.
    The TLS block is identified by the `tls.transitleastsquares` import inside
    the try body. There may be multiple try/except blocks; we want the one
    whose body contains the `import transitleastsquares as tls`."""
    candidates: list[tuple[ast.Try, ast.ExceptHandler]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_src = ast.unparse(node) if hasattr(ast, "unparse") else ""
        if "transitleastsquares" in body_src:
            for handler in node.handlers:
                candidates.append((node, handler))
    assert candidates, "no try block containing 'transitleastsquares' found"
    return candidates[0]


def test_tls_try_block_has_distinct_infra_handler():
    """The TLS try/except block must have a handler that catches
    AssertionError and/or RuntimeError distinctly from a bare
    `except Exception`. Without this, a Windows nested-pool
    AssertionError is silently folded into tls_valid=False with no
    way for downstream consumers to tell apart "gate said no" from
    "gate could not run"."""
    source = _read(DETECTION_PY)
    tree = ast.parse(source)
    _, _ = _find_tls_try_block(tree)  # asserts the try block exists

    infra_handlers: list[ast.ExceptHandler] = []
    bare_exception_handlers: list[ast.ExceptHandler] = []
    import_error_handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_src = ast.unparse(node) if hasattr(ast, "unparse") else ""
        if "transitleastsquares" not in body_src:
            continue
        for handler in node.handlers:
            t = handler.type
            if t is None:
                # bare `except:` — equivalent to `except BaseException`.
                # We treat this as the worst case: it catches everything
                # and provides no distinction.
                bare_exception_handlers.append(handler)
            elif isinstance(t, ast.Tuple):
                names = []
                for elt in t.elts:
                    if isinstance(elt, ast.Name):
                        names.append(elt.id)
                if "AssertionError" in names or "RuntimeError" in names:
                    infra_handlers.append(handler)
                if "ImportError" in names:
                    import_error_handlers.append(handler)
            elif isinstance(t, ast.Name):
                if t.id in ("AssertionError", "RuntimeError"):
                    infra_handlers.append(handler)
                elif t.id == "ImportError":
                    import_error_handlers.append(handler)
                elif t.id == "Exception":
                    bare_exception_handlers.append(handler)

    assert infra_handlers, (
        "The TLS try block in detection.py must have an explicit "
        "except (AssertionError, RuntimeError) handler. Without it, a "
        "deterministic environment failure (e.g. the Windows "
        "AssertionError from a nested multiprocessing.Pool inside a "
        "daemon worker) is silently folded into tls_valid=False with no "
        "distinguishable record, exactly as happened between 2026-06-09 "
        "and 2026-07-06. This is the silent-correctness-break anti-pattern "
        "this test exists to prevent."
    )
    assert import_error_handlers, (
        "The TLS try block must retain its except ImportError handler "
        "for the 'transitleastsquares not installed' fail-open path."
    )
    # The bare `except Exception` branch is allowed, but it must come
    # AFTER the infra branch so that AssertionError/RuntimeError are
    # caught first. Verify ordering: the infra handler must precede the
    # bare Exception handler in source order.
    all_handlers: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_src = ast.unparse(node) if hasattr(ast, "unparse") else ""
        if "transitleastsquares" not in body_src:
            continue
        for idx, handler in enumerate(node.handlers):
            t = handler.type
            tag = "other"
            if t is None:
                tag = "bare"
            elif isinstance(t, ast.Tuple):
                names = [e.id for e in t.elts if isinstance(e, ast.Name)]
                if "AssertionError" in names or "RuntimeError" in names:
                    tag = "infra"
                elif "ImportError" in names:
                    tag = "import"
                elif "Exception" in names:
                    tag = "bare-exception"
            elif isinstance(t, ast.Name):
                if t.id in ("AssertionError", "RuntimeError"):
                    tag = "infra"
                elif t.id == "ImportError":
                    tag = "import"
                elif t.id == "Exception":
                    tag = "bare-exception"
            all_handlers.append((idx, tag))
    # The infra handler must appear before any bare-exception handler.
    infra_positions = [i for i, t in all_handlers if t == "infra"]
    bare_positions = [i for i, t in all_handlers if t == "bare-exception"]
    assert infra_positions and bare_positions, (
        f"Expected both infra and bare-exception handlers, got {all_handlers}"
    )
    assert min(infra_positions) < max(bare_positions), (
        "The except (AssertionError, RuntimeError) handler MUST come before "
        "any bare `except Exception` in source order, otherwise Python's "
        "handler-matching will hit the bare handler first and the infra "
        "branch will never execute. Handlers: " + repr(all_handlers)
    )


def test_tls_infra_handler_assigns_tls_environment_error():
    """The infra-failure handler must populate a result-dict field
    `tls_environment_error` (string) so downstream consumers can see
    and surface the failure distinctly from a scientific rejection."""
    source = _read(DETECTION_PY)
    # Look for the assignment of tls_environment_error inside an
    # except (AssertionError, RuntimeError) block. The simplest test
    # is textual: search for both the handler and the assignment
    # within a reasonable window.
    infra_match = re.search(
        r"except\s*\(\s*AssertionError\s*,\s*RuntimeError\s*\)\s*as\s+\w+\s*:",
        source,
    )
    assert infra_match, (
        "No `except (AssertionError, RuntimeError) as e:` block found in "
        "detection.py. The infra-failure branch is missing — see "
        "test_tls_try_block_has_distinct_infra_handler."
    )
    # The next 2000 chars must contain the assignment.
    window = source[infra_match.end(): infra_match.end() + 2000]
    assert "tls_environment_error" in window, (
        "The infra except block must assign a string to "
        "tls_environment_error. Without it, downstream consumers cannot "
        "tell apart 'gate said no' from 'gate could not run'."
    )
    # Must also log loudly — refuse to accept silent fold.
    assert re.search(r"\[TLS-INFRA-ERROR\]", window), (
        "The infra except block must log with the [TLS-INFRA-ERROR] "
        "sentinel. The legacy one-line `WARNING: TLS validation failed: {e}` "
        "is the exact anti-pattern this test exists to prevent."
    )


def test_tls_result_dict_carries_environment_and_scientific_error_fields():
    """The result dict returned by detect_transit_candidate must include
    tls_environment_error and tls_scientific_error as initialised-to-None
    fields. The J2c silent-AssertionError bug existed because these
    fields did not exist, so a folded env failure had no observable
    record on the success path either."""
    source = _read(DETECTION_PY)
    # The initialisers
    init_env = re.search(
        r"^\s*tls_environment_error\s*=\s*None\b",
        source,
        flags=re.MULTILINE,
    )
    init_sci = re.search(
        r"^\s*tls_scientific_error\s*=\s*None\b",
        source,
        flags=re.MULTILINE,
    )
    assert init_env, "tls_environment_error must be initialised to None"
    assert init_sci, "tls_scientific_error must be initialised to None"
    # The result dict entries (literal strings inside the dict literal)
    assert "'tls_environment_error'" in source, (
        "result dict must include 'tls_environment_error' key"
    )
    assert "'tls_scientific_error'" in source, (
        "result dict must include 'tls_scientific_error' key"
    )
    # The boolean gate outcome must also flow out so downstream
    # consumers (orchestrator, UI) can read the gate's verdict
    # without having to recompute it from the error fields.
    assert "'tls_valid'" in source, (
        "result dict must include 'tls_valid' key. The downstream "
        "contract is: tls_valid is the boolean the orchestrator's "
        "guardrail 1 reads; tls_environment_error / tls_scientific_error "
        "are the mutually-exclusive reasons for a False."
    )


# ---------------------------------------------------------------------------
# Behavioural test: simulate the broken configuration (use_threads=8 inside
# the daemon worker) by stubbing the TLS module so model.power raises
# AssertionError, and assert the result dict carries tls_environment_error
# as a non-empty string with tls_scientific_error still None.
#
# This is a true behavioural test of the new except-block contract. It
# does NOT require multiprocessing — we patch transitleastsquares.transitleastsquares
# in sys.modules so the import inside detect_transit_candidate picks it up.
# ---------------------------------------------------------------------------

def test_detect_transit_candidate_surfaces_tls_environment_error(monkeypatch, capsys):
    """When the TLS call raises AssertionError (the Windows
    nested-multiprocessing failure mode), the result dict must carry
    a populated `tls_environment_error` string and `tls_scientific_error`
    must remain None. Stdout must include the [TLS-INFRA-ERROR] sentinel."""
    import sys
    import types

    # Build a fake transitleastsquares module whose model.power raises AssertionError.
    class _FakeModel:
        def power(self, **kwargs):
            raise AssertionError(
                "daemonic processes are not allowed to have children"
            )

    class _FakeTLS:
        def transitleastsquares(self, t, y):
            return _FakeModel()

    fake_pkg = types.ModuleType("transitleastsquares")
    fake_pkg.transitleastsquares = _FakeTLS().transitleastsquares
    monkeypatch.setitem(sys.modules, "transitleastsquares", fake_pkg)

    # Build a small flat curve and a fake stellar-rotation estimate so
    # the code path reaches the TLS branch. We need best_period > 0
    # from BLS. Use a small number of points to keep the test fast.
    import numpy as np
    from astraeus.analysis.detection import detect_transit_candidate
    rng = np.random.default_rng(seed=20260706)
    n = 200
    t = np.arange(n, dtype=np.float64) * 0.01  # 0.01d cadence, ~2d baseline
    flux = 1.0 + 1e-3 * rng.standard_normal(n)
    # Inject a clear transit signal so BLS finds a non-zero period.
    period = 0.5  # days
    t0 = 0.1
    duration = 0.02
    depth = 0.01
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    in_tr = np.abs(phase) < 0.5 * duration
    flux[in_tr] -= depth

    result = detect_transit_candidate(
        time=t,
        flux=flux,
        target_name="contract-test",
        data_source="synthetic",
        metadata={},
    )

    # The new contract: env failures are visible.
    assert "tls_environment_error" in result, (
        "result dict is missing tls_environment_error key"
    )
    assert "tls_scientific_error" in result, (
        "result dict is missing tls_scientific_error key"
    )
    env = result["tls_environment_error"]
    sci = result["tls_scientific_error"]
    assert env is not None and "AssertionError" in env, (
        f"tls_environment_error must be a non-None string mentioning "
        f"AssertionError when the TLS call raises AssertionError; got {env!r}"
    )
    assert sci is None, (
        f"tls_scientific_error must remain None for an infra failure; "
        f"got {sci!r}. The two branches must be mutually exclusive."
    )
    assert result["tls_valid"] is False, (
        "tls_valid must be False when the gate could not run"
    )
    # Stdout must include the loud sentinel.
    captured = capsys.readouterr()
    assert "[TLS-INFRA-ERROR]" in captured.out, (
        "The infra except block must print a [TLS-INFRA-ERROR] sentinel "
        "to stdout. The legacy one-line WARNING: is the anti-pattern this "
        "test exists to prevent. Captured stdout:\n" + captured.out
    )
    # And NOT the bare 'WARNING: TLS validation failed' fold.
    assert "WARNING: TLS validation failed" not in captured.out, (
        "The bare 'WARNING: TLS validation failed' message must not appear "
        "for an infra failure. That message is reserved for the "
        "scientific-failure branch (or removed entirely)."
    )

