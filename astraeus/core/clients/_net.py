"""Network seam — HttpClientPort, HttpResponse, and concrete clients.

Phase 0 of the data-ingestion SOLID/SRP refactor (see
``docs/superpowers/specs/2026-06-30-data-ingestion-solid-refactor-design.md``
section "Approach" and Phase 0, step 0.1) lands these types without
rewiring any production caller. Subsequent phases plug ``MastStreamer``,
``S3FallbackDownloader``, ``TapClient``, and ``PsCompanion`` onto this
port.

Why a port rather than direct ``requests`` calls
-----------------------------------------------
The current ``lightkurve_client`` module calls ``requests.get`` /
``requests.head`` at four distinct sites (MAST stream, S3 fallback,
NASA TAP, PS companion). Each carries its own timeout semantics, error
classification, and fixture requirements. Collapsing them onto a single
``HttpClientPort`` lets:

* Tests inject ``FakeHttpClient`` to record calls and serve scripted
  responses from ``tests/_fixtures/http_responses/``.
* Future collaborators (e.g. a Gaia archive client) plug in without
  duplicating HTTP plumbing.
* The fixture-recorder CLI (Phase 0 step 0.4) sit at a single entry
  point.

Streaming model
---------------
The HTTP boundary splits into two modes:

* **Buffered** (``stream=False``): the body is fully drained into
  ``HttpResponse.body``. ``iter_chunks`` is ``None``.
* **Streaming** (``stream=True``): the body is *not* drained. The
  underlying response stays open and ``iter_chunks(chunk_size)`` returns
  a fresh iterator that yields ``bytes`` slices. The response is closed
  when that iterator is exhausted (or garbage-collected). This is the
  mode FIX 2.3 (TESS FFI streaming, ≥600 s read timeout) relies on.

Timeout semantics
-----------------
``timeout`` is a single ``float`` applied to the full request, per the
``requests`` library convention when given a scalar. Collaborators
that need a ``(connect, read)`` tuple (e.g. ``MastStreamer`` for FIX
2.3's TESS FFI streaming at ≥600 s read timeout) compose an adapter
locally rather than widening this port — production code stays on a
predictable, single-typed contract.

The matching test double lives at ``tests/_fixtures/fakes.py``
(``FakeHttpClient``), not here, so production code carries no
test-only artifacts.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import requests


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class HttpClientPort(Protocol):
    """Contract for collaborators that fetch from MAST, S3, NASA TAP, PS, etc.

    Implementations must be safe to call from multiple threads. The
    production implementation (``RequestsHttpClient``) delegates to
    ``requests.Session`` which is itself thread-safe at the connection
    pool level.
    """

    def get(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        stream: bool = False,
    ) -> HttpResponse:
        """Issue an HTTP GET.

        ``timeout`` is a single ``float`` applied to the whole request.
        Collaborators that need a ``(connect, read)`` tuple wrap this
        port locally.

        When ``stream`` is ``True`` the body is *not* drained; the
        caller iterates via ``HttpResponse.iter_chunks`` and the
        underlying connection is released when iteration completes.
        """

        ...

    def head(self, url: str, *, timeout: float = 30.0) -> HttpResponse:
        """Issue an HTTP HEAD. Always buffered (no body)."""

        ...


# ---------------------------------------------------------------------------
# Response container
# ---------------------------------------------------------------------------


@dataclass
class HttpResponse:
    """Normalized HTTP response returned by every ``HttpClientPort`` impl.

    ``body`` and ``iter_chunks`` are mutually exclusive:

    * Buffered responses (``stream=False``) populate ``body`` and leave
      ``iter_chunks`` as ``None``.
    * Streaming responses (``stream=True``) leave ``body`` empty (or
      partially populated if the caller iterates without consuming) and
      populate ``iter_chunks`` with a factory that yields byte chunks.

    ``headers`` are lower-cased on insertion to make lookup tolerant —
    the production MAST endpoint mixes cases.
    """

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    iter_chunks: Callable[[int], Iterator[bytes]] | None = None

    def header(self, name: str, default: str | None = None) -> str | None:
        """Case-insensitive header lookup."""
        return self.headers.get(name.lower(), default)


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------


class RequestsHttpClient:
    """``HttpClientPort`` backed by the ``requests`` library.

    Used by all production collaborators (MastStreamer, S3Fallback,
    TapClient, PsCompanion) once Phase 2+ lands. In Phase 0 this class
    has no callers — it exists so the seam shape is fixed and tests
    can exercise it directly.
    """

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    # -- HttpClientPort ----------------------------------------------------

    def get(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        stream: bool = False,
    ) -> HttpResponse:
        resp = self._session.get(url, timeout=timeout, stream=stream)
        if stream:
            return HttpResponse(
                status_code=resp.status_code,
                headers=_lower_headers(resp.headers),
                body=b"",
                iter_chunks=_make_chunk_iter(resp),
            )
        # Buffered: drain now so the caller sees a fully-populated body.
        body = resp.content
        resp.close()
        return HttpResponse(
            status_code=resp.status_code,
            headers=_lower_headers(resp.headers),
            body=body,
            iter_chunks=None,
        )

    def head(self, url: str, *, timeout: float = 30.0) -> HttpResponse:
        resp = self._session.head(url, timeout=timeout, allow_redirects=True)
        body = resp.content
        resp.close()
        return HttpResponse(
            status_code=resp.status_code,
            headers=_lower_headers(resp.headers),
            body=body,
            iter_chunks=None,
        )


def _lower_headers(headers: requests.structures.CaseInsensitiveDict) -> dict[str, str]:
    """Return a plain dict with lower-cased keys (matches the spec)."""
    return {k.lower(): v for k, v in headers.items()}


def _make_chunk_iter(resp: requests.Response) -> Callable[[int], Iterator[bytes]]:
    """Wrap a live ``requests.Response`` as a chunk iterator factory.

    The returned callable closes the response when the iterator it
    yields is exhausted. This keeps connection-pool slots from leaking
    during long TESS FFI downloads.
    """

    def iter_chunks(chunk_size: int) -> Iterator[bytes]:
        try:
            yield from resp.iter_content(chunk_size=chunk_size)
        finally:
            resp.close()

    return iter_chunks


# ---------------------------------------------------------------------------
# Fixture recorder CLI (Phase 0, step 0.4)
# ---------------------------------------------------------------------------


def _record_one(client: RequestsHttpClient, url: str, *, timeout: float = 30.0) -> dict:
    """Issue a single GET against ``url`` and serialise the response."""
    resp = client.get(url, timeout=timeout, stream=False)
    return {
        "url_pattern": url,
        "method": "GET",
        "status": resp.status_code,
        "headers": resp.headers,
        "body_b64": base64.b64encode(resp.body).decode("ascii"),
        "chunk_iter": None,
    }


def _record_fixture(target: str, mission: str, out_dir: Path) -> list[Path]:
    """Capture one or more HTTP responses for ``target``/``mission``.

    Phase 0 ships a minimal recorder: it captures a single MAST
    download URL. Subsequent phases extend the URL table as
    characterisation expands.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    client = RequestsHttpClient()
    captured: list[Path] = []
    url = f"https://mast.stsci.edu/api/v0/Download/file?target={target}&mission={mission}"
    fixture_path = out_dir / f"mast_{mission.lower()}_{target.lower()}_200.json"
    fixture_path.write_text(json.dumps(_record_one(client, url), indent=2))
    captured.append(fixture_path)
    return captured


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astraeus.core.clients._net",
        description="Fixture recorder for the HttpClientPort seam.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Capture HTTP fixtures for a target.")
    rec.add_argument("--target", required=True, help="Canonical target name, e.g. TRAPPIST-1")
    rec.add_argument("--mission", required=True, choices=["TESS", "Kepler", "K2"])
    rec.add_argument(
        "--out-dir",
        default="tests/_fixtures/http_responses",
        help="Directory to write JSON fixtures into.",
    )

    args = parser.parse_args(argv)
    if args.cmd == "record":
        out_dir = Path(args.out_dir)
        paths = _record_fixture(args.target, args.mission, out_dir)
        for p in paths:
            print(p)
        return 0
    return 2  # pragma: no cover — argparse "required=True" guards this


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())