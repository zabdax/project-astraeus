"""Scientific backend capability reporting and fail-closed semantics.

Phase 0 introduces this module to eliminate *silent scientific
degradation* (PRD v4.1 §4.2).  Before this module existed, ``batman``,
``wotan`` and ``transitleastsquares`` were undeclared optional
dependencies whose absence changed scientific output without raising
any error, warning, result field, or job state -- a missing TLS gate
was recorded as ``tls_valid = True``.

Three concepts live here:

* :class:`BackendId` -- the scientific backends the engine depends on.
* :class:`CapabilitySnapshot` -- a structured "which backends are
  importable" record.  Deliberately *not* a single vague boolean.
* :class:`TlsOutcome` -- the four-valued replacement for the boolean
  ``tls_valid`` as the authoritative scientific state.  It makes it
  impossible to confuse "TLS passed", "TLS rejected the candidate",
  "TLS could not execute", and "TLS was not attempted".

Design rules (PRD v4.1 §5 / §22):

* The representation is stable enough that Phase 1's ``AnalysisResult``
  can adopt ``CapabilitySnapshot`` without a redesign -- it exposes a
  plain JSON-serializable dict keyed by backend short name.
* Adding a future scientific backend means adding one enum member and
  one import name; no rewrite.
* The completeness subsystem (``simulation/completeness.py``) is the
  in-repo precedent for versioned, hashable config payloads; the
  ``snapshot_version`` field follows that pattern so a cached result
  can be invalidated when the capability set changes.

This module performs no scientific computation and imports no heavy
backends eagerly -- availability is probed lazily so importing
``astraeus`` never costs a TLS import.
"""

from __future__ import annotations

import enum
import importlib.util
import logging
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List

__all__ = [
    "BackendId",
    "TlsOutcome",
    "CapabilitySnapshot",
    "BackendUnavailable",
    "capability_snapshot",
    "is_backend_available",
    "require_backend",
    "get_logger",
    "SUBTRACTION_BACKEND_BATMAN",
    "SUBTRACTION_BACKEND_TRAPEZOID",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOGGER_NAME = "astraeus"


class _StdoutHandler(logging.StreamHandler):
    """A ``StreamHandler`` that resolves ``sys.stdout`` at emit time.

    Python's logging defaults to ``sys.stderr``, but astraeus's
    worker-oriented scientific warnings are consumed by the
    orchestrator's stdout event channel, and the TLS infra-failure
    contract (``tests/characterize/test_tls_call_path_contract.py``)
    asserts the ``[TLS-INFRA-ERROR]`` sentinel on stdout.  Resolving
    the stream lazily (rather than binding it at construction) keeps
    captured-stdout test fixtures working: the handler always sees the
    currently-installed ``sys.stdout``.
    """

    def __init__(self) -> None:
        # Skip StreamHandler.__init__'s stream binding; we resolve it
        # dynamically via the property below.
        logging.Handler.__init__(self)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, value) -> None:  # noqa: ARG002 - intentionally inert
        # Handler.__init__ and StreamHandler both assign self.stream;
        # the property is the single source of truth, so discard writes.
        return


def get_logger(name: str = "") -> logging.Logger:
    """Return a logger under the ``astraeus`` namespace.

    The ``astraeus`` logger is configured once with a stdout handler at
    WARNING level.  Idempotency is checked by handler type rather than a
    module flag so that an ``importlib.reload`` of this module cannot
    attach a duplicate handler to the persistent logger object.

    Callers should NOT reconfigure this logger; scientific warnings that
    affect result validity must reach the caller, and a second handler
    configuration would silently drop or duplicate them.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if not any(isinstance(h, _StdoutHandler) for h in logger.handlers):
        handler = _StdoutHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logger


logger = get_logger("capabilities")


# ---------------------------------------------------------------------------
# Backend identity
# ---------------------------------------------------------------------------


class BackendId(str, enum.Enum):
    """The scientific backends the engine depends on.

    The enum *value* is the short name used in result payloads
    (``backends_available``); the import name is resolved via
    :data:`_IMPORT_NAMES`.
    """

    BATMAN = "batman"
    WOTAN = "wotan"
    TLS = "tls"


_IMPORT_NAMES: Dict[BackendId, str] = {
    BackendId.BATMAN: "batman",
    BackendId.WOTAN: "wotan",
    # The distribution is ``transitleastsquares``; the import name is
    # the same.  The short payload key stays "tls" per PRD §22.
    BackendId.TLS: "transitleastsquares",
}


# Subtraction-backend identifiers reported on the orchestrator's
# subtraction provenance (PRD §4.2 / §10).  ``batman`` is the preferred
# backend; the trapezoid model is a *scientifically different* fallback
# (zero limb darkening, no curvature) and must never be represented as
# equivalent to it.
SUBTRACTION_BACKEND_BATMAN = "batman"
SUBTRACTION_BACKEND_TRAPEZOID = "trapezoid"


class TlsOutcome(str, enum.Enum):
    """The four possible outcomes of the TLS cross-validation gate.

    Replaces the boolean ``tls_valid`` as the authoritative scientific
    state (PRD v4.1 §4.2 item 3).  ``tls_valid`` is retained on result
    dicts for backwards compatibility with existing consumers, but it
    is now derived from this enum rather than being the source of
    truth.

    The four values are mutually exclusive and scientifically distinct:

    * ``ran_pass`` -- TLS executed and validated the candidate.
    * ``ran_fail`` -- TLS executed and rejected the candidate. This is a
      valid *negative scientific result*.
    * ``env_unavailable`` -- TLS could not execute because the
      environment is invalid (package missing, or the
      ``AssertionError``/``RuntimeError`` infrastructure failure mode
      locked by ``test_tls_call_path_contract.py``). This is neither a
      pass nor a scientific rejection; a production run that reaches
      this state has *failed*, not "found zero candidates".
    * ``not_attempted`` -- the engine deliberately did not invoke the
      gate (e.g. BLS returned no period to validate).
    """

    RAN_PASS = "ran_pass"
    RAN_FAIL = "ran_fail"
    ENV_UNAVAILABLE = "env_unavailable"
    NOT_ATTEMPTED = "not_attempted"


class BackendUnavailable(RuntimeError):
    """Raised when a required scientific backend is not usable.

    This is a *structured* failure: it carries the :class:`BackendId`
    so callers can produce an explicit human-readable reason and mark
    the execution FAILED, instead of degrading silently to a different
    algorithm (PRD v4.1 §4.2 item 2 / §7).

    Note that this subclasses ``RuntimeError``.  ``detection.py``'s TLS
    block treats a bare ``RuntimeError`` from the TLS call as an
    *infrastructure* failure, so this exception must be raised outside
    that try block (at capability-check time), never inside it.
    """

    def __init__(self, backend: BackendId, detail: str = "") -> None:
        self.backend = backend
        self.detail = detail
        message = (
            f"Required scientific backend '{backend.value}' is unavailable"
            + (f": {detail}" if detail else "")
            + ". Install it (see pyproject.toml [project.dependencies]) or "
            "set ASTRAEUS_ALLOW_MISSING_BACKENDS=1 for a non-production "
            "diagnostic run. A missing backend is a FAILED run, never a "
            "silently-degraded scientific result."
        )
        super().__init__(message)


# ---------------------------------------------------------------------------
# Capability snapshot
# ---------------------------------------------------------------------------

#: Bumped when the set of tracked backends or the probing logic changes,
#: so a cached result carrying an older snapshot is detectably stale.
#: Follows the completeness subsystem's ``algo_version`` precedent.
SNAPSHOT_VERSION = 1

#: Set to opt into explicit, *non-production* fallback behaviour for
#: diagnostic runs (developer machines, quick smoke checks).  Production
#: paths never read this: they call :func:`require_backend`.
_ALLOW_MISSING_ENVVAR = "ASTRAEUS_ALLOW_MISSING_BACKENDS"


@dataclass(frozen=True)
class CapabilitySnapshot:
    """Structured record of which scientific backends are importable.

    Deliberately replaces any single ``scientific_backend_available``
    boolean (PRD v4.1 §5): the three backends are independent, and
    "wotan present but TLS missing" is a different operational situation
    from "everything missing".
    """

    batman: bool
    wotan: bool
    tls: bool
    snapshot_version: int = SNAPSHOT_VERSION

    @classmethod
    def current(cls) -> "CapabilitySnapshot":
        """Probe the interpreter for every tracked backend, once."""
        return cls(
            batman=is_backend_available(BackendId.BATMAN),
            wotan=is_backend_available(BackendId.WOTAN),
            tls=is_backend_available(BackendId.TLS),
        )

    def available(self) -> Dict[str, bool]:
        """Return the PRD §22 payload shape: ``{batman, wotan, tls}``."""
        return {
            BackendId.BATMAN.value: self.batman,
            BackendId.WOTAN.value: self.wotan,
            BackendId.TLS.value: self.tls,
        }

    def is_available(self, backend: BackendId) -> bool:
        return bool(self.available()[backend.value])

    def missing(self, backends: Iterable[BackendId]) -> List[BackendId]:
        """Return the subset of ``backends`` that are NOT available."""
        return [b for b in backends if not self.is_available(b)]

    def to_dict(self) -> Dict[str, object]:
        """JSON-serializable form for result payloads and provenance."""
        payload: Dict[str, object] = dict(self.available())
        payload["snapshot_version"] = self.snapshot_version
        return payload


def is_backend_available(backend: BackendId) -> bool:
    """Return True iff the backend's module is importable right now.

    Uses ``importlib.util.find_spec`` rather than importing, so probing
    never pays the import cost and never executes third-party
    module-level code.
    """
    try:
        return importlib.util.find_spec(_IMPORT_NAMES[backend]) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        # find_spec raises ValueError for relative/invalid names and
        # ModuleNotFoundError if a parent package is missing.
        return False


def capability_snapshot() -> CapabilitySnapshot:
    """Module-level convenience accessor (mirrors the PRD's phrasing)."""
    return CapabilitySnapshot.current()


def missing_backends_allowed() -> bool:
    """True only if the operator explicitly accepted degraded science.

    Production callers must NOT gate on this; it exists so that a
    developer can run a quick diagnostic without the fail-closed raise.
    Any run performed under this flag is explicitly *not* a production
    scientific result.
    """
    import os

    return os.environ.get(_ALLOW_MISSING_ENVVAR, "").strip() not in ("", "0", "false", "False")


def require_backend(backend: BackendId) -> None:
    """Fail closed for a production scientific run.

    Raises :class:`BackendUnavailable` when ``backend`` is missing and
    the operator has not explicitly opted into degraded diagnostics.
    Call this at the boundary of a production scientific path, before
    the algorithm that needs the backend runs -- never inside a broad
    ``except Exception`` that would fold the structured error back into
    an opaque failure.
    """
    if is_backend_available(backend):
        return
    if missing_backends_allowed():
        logger.warning(
            "[CAPABILITY] Scientific backend '%s' is unavailable; "
            "continuing under %s=1. This run is NOT a production "
            "scientific result and must not be reported as one.",
            backend.value,
            _ALLOW_MISSING_ENVVAR,
        )
        return
    logger.error("[CAPABILITY] Required backend '%s' unavailable; failing closed.", backend.value)
    raise BackendUnavailable(backend, "module is not importable")
