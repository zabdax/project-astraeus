"""Filesystem seam — FsPort + RealFs + FakeFs.

Phase 0 of the data-ingestion SOLID/SRP refactor (see
``docs/superpowers/specs/2026-06-30-data-ingestion-solid-refactor-design.md``
section "Filesystem & clock intercepts" and Phase 0, step 0.2) lands
this seam without rewiring any production caller.

Why a port rather than direct ``os``/``shutil`` calls
------------------------------------------------------
The current ``lightkurve_client`` module pokes the filesystem at ~15
sites — cache directory creation, atomic-download temp files, FITS
validation reads, recursive directory wipes, etc. Each site carries
its own assumptions (idempotent makedirs, missing-file tolerance,
streaming-write semantics). Putting them behind ``FsPort`` lets:

* Tests inject ``FakeFs`` (in ``tests/_fixtures/fakes.py``) to record
  every operation and stage scripted filesystem states.
* Future collaborators swap in a sandboxed implementation (e.g. for
  Streamlit Cloud's read-only filesystem) without rewriting call
  sites.

Spec surface vs. real usage
---------------------------
The spec Protocol (section "Filesystem & clock intercepts") defines
the four most-frequent operations: ``makedirs``, ``exists``,
``remove``, ``open``. The current ``lightkurve_client`` module also
uses ``os.path.isdir``, ``os.path.getsize``, ``shutil.rmtree``,
``os.walk``, and ``tempfile.NamedTemporaryFile``. Phase 0 lands the
spec-literal surface; Phase 2 (``CacheManager``, ``MastStreamer``,
``DownloadCache``) widens the port as collaborators extract each
behaviour. The widening decisions are deliberately left to the
implementation plan, not baked into Phase 0.

Streaming model
---------------
``FsPort.open`` returns a plain file-like object (binary mode). The
production ``RealFs`` returns ``IO[bytes]``; ``FakeFs`` returns an
``io.BytesIO`` so writes are recorded in memory without touching disk.
"""

from __future__ import annotations

import os
import shutil
from typing import IO, Protocol


class FsPort(Protocol):
    """Contract for filesystem operations on cache dirs, download temps, and FITS files."""

    def makedirs(self, path: str, exist_ok: bool) -> None:
        """Create ``path`` (and parents) as a directory.

        ``exist_ok=True`` matches ``os.makedirs(..., exist_ok=True)`` —
        callers depend on this being idempotent.
        """

        ...

    def exists(self, path: str) -> bool:
        """Return ``True`` if ``path`` exists (file or directory)."""

        ...

    def remove(self, path: str) -> None:
        """Remove a file.

        Behaviour on missing paths is implementation-defined; the
        production ``RealFs`` mirrors ``os.remove`` (raises ``FileNotFoundError``).
        """

        ...

    def open(self, path: str, mode: str) -> IO[bytes]:
        """Open ``path`` in ``mode`` and return a binary file-like object.

        ``mode`` follows the built-in ``open()`` conventions but is
        restricted to ``"rb"`` / ``"wb"`` by current callers. Callers
        must close the returned object.
        """

        ...


class RealFs:
    """``FsPort`` backed by the real filesystem (``os`` / ``shutil`` / built-in ``open``).

    Used by all production collaborators once Phase 2+ lands. In
    Phase 0 this class has no callers — it exists so the seam shape
    is fixed and tests can exercise it directly.
    """

    def makedirs(self, path: str, exist_ok: bool) -> None:
        os.makedirs(path, exist_ok=exist_ok)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def remove(self, path: str) -> None:
        os.remove(path)

    def open(self, path: str, mode: str) -> IO[bytes]:
        return open(path, mode)


# Re-exported helpers used by Phase 2 collaborators. Keeping them here
# (instead of duplicating in collaborators) lets the RealFs impl stay
# a thin pass-through while exposing the rest of the filesystem API
# that ``lightkurve_client`` actually uses.
def rmtree(path: str, ignore_errors: bool = False) -> None:
    """Convenience wrapper for ``shutil.rmtree``."""
    shutil.rmtree(path, ignore_errors=ignore_errors)


def isdir(path: str) -> bool:
    return os.path.isdir(path)


def getsize(path: str) -> int:
    return os.path.getsize(path)


def join(*parts: str) -> str:
    return os.path.join(*parts)


def dirname(path: str) -> str:
    return os.path.dirname(path)


def expanduser(path: str) -> str:
    return os.path.expanduser(path)