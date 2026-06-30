"""Clock seam — ClockPort + RealClock + FakeClock.

Phase 0 of the data-ingestion SOLID/SRP refactor (see
``docs/superpowers/specs/2026-06-30-data-ingestion-solid-refactor-design.md``
section "Filesystem & clock intercepts" and Phase 0, step 0.2) lands
this seam without rewiring any production caller.

Why a port rather than direct ``time`` calls
--------------------------------------------
``lightkurve_client`` uses ``time.sleep`` for retry backoff
(``_STREAM_BACKOFF_BASE`` exponentiation, ``_TESS_LC_RETRY_BACKOFF``
multiplier) and could in principle read ``time.time`` for cache-stale
checks. Putting both behind a port lets:

* Tests inject ``FakeClock`` (in ``tests/_fixtures/fakes.py``) so
  backoff loops finish in microseconds rather than seconds.
* Deterministic timestamps in characterization tests.

Spec surface vs. real usage
---------------------------
The spec Protocol defines ``now()`` and ``sleep()``. The current
``lightkurve_client`` module only calls ``time.sleep`` (backoff) and
``time.monotonic`` would be a cleaner choice for measuring elapsed
time, but no collaborator currently does so. Phase 0 lands the
spec-literal surface; Phase 2 widens if a collaborator needs
``monotonic()``.
"""

from __future__ import annotations

import time
from typing import Protocol


class ClockPort(Protocol):
    """Contract for time access used by retry backoff and timing measurements."""

    def now(self) -> float:
        """Return the current wall-clock time in seconds since the epoch.

        Production uses ``time.time()``; tests inject a fake that
        advances on demand.
        """

        ...

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds``.

        Tests inject a fake that records the requested duration
        without actually sleeping, so backoff loops run instantly.
        """

        ...


class RealClock:
    """``ClockPort`` backed by ``time.time`` / ``time.sleep``."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)