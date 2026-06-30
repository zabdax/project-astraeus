"""Test-only fakes for the data-ingestion collaborators.

This module is the home for every test double referenced by Phase 1's
characterization suite. It sits at ``tests/_fixtures/fakes.py`` (not
inside the production package) so that production builds remain free
of test-only artifacts.

Each fake implements one of the Phase 0 seam Protocols:

* ``FakeHttpClient`` → ``astraeus.core.clients._net.HttpClientPort``
* ``FakeFs``         → ``astraeus.core.clients._fs.FsPort``
* ``FakeClock``      → ``astraeus.core.clients._clock.ClockPort``
* ``FakeLightkurveRow`` / ``FakeSearchResult`` →
  ``astraeus.core.clients.lightkurve_row.LightkurveRowPort``
  (and the implicit search-result-iterable contract)

See ``docs/superpowers/specs/2026-06-30-data-ingestion-solid-refactor-design.md``
section "Network Intercept Layer" (line 463) for the original spec.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import IO, Any

from astraeus.core.clients._net import HttpResponse


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class FakeHttpClient:
    """In-memory ``HttpClientPort`` for tests and the fixture-recorder CLI.

    Each call appends a ``RecordedCall`` to ``self.calls`` and returns
    the next scripted response from ``self.scripted`` (or a default
    200-with-empty-body response when the script is exhausted).

    Tests preload ``scripted`` with explicit ``HttpResponse`` instances;
    Phase 0 step 0.5 populates it from on-disk JSON manifests under
    ``tests/_fixtures/http_responses/``.
    """

    @dataclass
    class RecordedCall:
        method: str  # "GET" | "HEAD"
        url: str
        timeout: float
        stream: bool

    def __init__(self) -> None:
        self.calls: list[FakeHttpClient.RecordedCall] = []
        self.scripted: list[HttpResponse] = []

    # -- HttpClientPort ----------------------------------------------------

    def get(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        stream: bool = False,
    ) -> HttpResponse:
        self.calls.append(self.RecordedCall("GET", url, timeout, stream))
        return self._next_response()

    def head(self, url: str, *, timeout: float = 30.0) -> HttpResponse:
        self.calls.append(self.RecordedCall("HEAD", url, timeout, False))
        return self._next_response()

    # -- Scripting helpers -------------------------------------------------

    def _next_response(self) -> HttpResponse:
        if self.scripted:
            return self.scripted.pop(0)
        return HttpResponse(status_code=200, headers={}, body=b"", iter_chunks=None)

    def queue(self, response: HttpResponse) -> None:
        """Append a single scripted response to the queue."""
        self.scripted.append(response)


# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------


@dataclass
class FakeFsCall:
    op: str  # "makedirs" | "exists" | "remove" | "open"
    path: str
    kwargs: dict[str, Any] = field(default_factory=dict)


class FakeFs:
    """In-memory ``FsPort`` for tests.

    Files created via ``open(path, "wb")`` are stored in
    ``self.files`` keyed by path. ``exists`` consults both the
    explicit-file map and an optional ``self.dirs`` set so tests can
    pre-stage directory structure.

    All operations append to ``self.calls`` so tests can assert the
    sequence of FS interactions.
    """

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()
        self.calls: list[FakeFsCall] = []

    # -- FsPort ------------------------------------------------------------

    def makedirs(self, path: str, exist_ok: bool) -> None:
        self.calls.append(FakeFsCall("makedirs", path, {"exist_ok": exist_ok}))
        # Mirror os.makedirs(..., exist_ok=True) semantics: store
        # every parent so later `exists` calls see the full path.
        # Normalise to forward slashes; preserve a leading slash if
        # present so callers can use either form.
        norm = path.replace("\\", "/")
        has_leading = norm.startswith("/")
        parts = [p for p in norm.split("/") if p]
        for i in range(1, len(parts) + 1):
            joined = "/".join(parts[:i])
            if has_leading:
                joined = "/" + joined
            self.dirs.add(joined)

    def exists(self, path: str) -> bool:
        self.calls.append(FakeFsCall("exists", path))
        return path in self.files or path in self.dirs

    def remove(self, path: str) -> None:
        self.calls.append(FakeFsCall("remove", path))
        self.files.pop(path, None)
        self.dirs.discard(path)

    def open(self, path: str, mode: str) -> IO[bytes]:
        self.calls.append(FakeFsCall("open", path, {"mode": mode}))
        if "w" in mode:
            buf = io.BytesIO()

            def _on_close() -> None:
                self.files[path] = buf.getvalue()

            buf.close = _on_close  # type: ignore[method-assign]
            return buf
        # Read mode
        return io.BytesIO(self.files.get(path, b""))

    # -- Test helpers ------------------------------------------------------

    def stage_file(self, path: str, content: bytes) -> None:
        """Pre-populate a file as if it already existed on disk."""
        self.files[path] = content

    def stage_dir(self, path: str) -> None:
        """Pre-populate a directory as if it already existed."""
        self.dirs.add(path)


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


@dataclass
class FakeClockCall:
    seconds: float


class FakeClock:
    """In-memory ``ClockPort`` for tests.

    ``now()`` returns ``self.now_value`` (a float). ``sleep()`` records
    the requested duration to ``self.sleep_calls`` and advances
    ``now_value`` by the same amount so backoff loops terminate
    instantly without actually sleeping.
    """

    def __init__(self, start: float = 0.0) -> None:
        self.now_value: float = start
        self.sleep_calls: list[FakeClockCall] = []

    # -- ClockPort ---------------------------------------------------------

    def now(self) -> float:
        return self.now_value

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(FakeClockCall(seconds))
        self.now_value += seconds


# ---------------------------------------------------------------------------
# Lightkurve row + search result
# ---------------------------------------------------------------------------


@dataclass
class FakeLightkurveRow:
    """In-memory test double for a single lightkurve row.

    ``download_path`` is the on-disk path the fake will report when
    ``download()`` is called. Tests can populate a real temp FITS file
    there and assert collaborators read it.

    ``products`` defaults to an empty list so the default ctor is safe;
    collaborators that read products should construct a row with an
    explicit list.
    """

    download_path: str | None = None
    products: list[Any] = field(default_factory=list)
    download_calls: int = 0

    def download(self) -> Any:
        self.download_calls += 1
        return self.download_path

    def __iter__(self) -> Iterator["FakeLightkurveRow"]:  # pragma: no cover
        # Rows themselves aren't iterated; ``FakeSearchResult`` covers
        # that. This stub keeps type-checkers happy if a row is ever
        # iterated directly.
        yield self


@dataclass
class FakeSearchResult:
    """In-memory iterable of ``FakeLightkurveRow`` for tests.

    Mirrors the spec's ``search_result.__iter__`` surface and also
    exposes ``__len__`` so collaborators that need to count rows
    (added in Phase 2 port-widening) can be exercised.
    """

    rows: list[FakeLightkurveRow] = field(default_factory=list)

    def __iter__(self) -> Iterator[FakeLightkurveRow]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)