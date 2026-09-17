"""CWD-independent artifact and data-root resolution.

Phase 0 (PRD v4.1 §4.4 / §15).  Before this module, every artifact path
in the engine was relative to the process's current working directory
(``logging.py`` hardcoded ``os.path.join("logs", "experiments.json")``;
``outputs/`` and ``outputs/reports/`` were likewise CWD-relative).  A
CLI invocation from ``/`` or an installed package therefore either wrote
artifacts somewhere unexpected or failed outright.

Resolution order for the data root (highest priority first):

1. ``ASTRAEUS_DATA_DIR``   -- explicit override (tests + CI).
2. A source checkout       -- the package directory sits inside the
   repository root, so artifacts stay in-repo for developer runs and
   the existing test fixtures keep working unchanged.
3. An XDG-style user dir    -- ``$XDG_DATA_HOME/astraeus`` or
   ``~/.local/share/astraeus`` when the package is installed into
   ``site-packages`` and no repository is present.

``ASTRAEUS_PROJECT_ROOT`` overrides the *repository* detection (step 2)
only; it does not change the data root unless the source-checkout branch
is taken.

This is deliberately not a full configuration system (Phase 1 owns
``AnalysisConfig``); it is the minimum deterministic resolution the
packaging/CLI foundation requires.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "project_root",
    "data_root",
    "artifact_path",
    "ensure_dir",
]

# The package is laid out flat: <repo>/astraeus/core/paths.py, so the
# package directory is two parents up from this file and the *repository*
# root is three. We locate the repo root by searching upward for a marker
# rather than hardcoding the depth: this stays correct if the package
# tree is re-laid-out, and -- importantly -- never silently redirects
# developer artifacts to the XDG user directory just because a parent
# level was miscounted.
_PACKAGE_DIR = Path(__file__).resolve().parent.parent

# Files that identify a checkout of this repository. If none is present
# above the package, we assume an installed (site-packages) copy.
_REPO_MARKERS = ("pyproject.toml", ".git", "pytest.ini")

# Bound the upward walk: an installed package's parents (site-packages,
# the interpreter dir, the user profile) must never be mistaken for a
# repository even if a stray marker happens to appear up there.
_MAX_REPO_SEARCH_LEVELS = 5

_PROJECT_ROOT_ENV = "ASTRAEUS_PROJECT_ROOT"
_DATA_DIR_ENV = "ASTRAEUS_DATA_DIR"
_XDG_DATA_HOME_ENV = "XDG_DATA_HOME"


def _find_repo_root() -> Path | None:
    """Walk upward from the package dir looking for a repository marker.

    Returns the first ancestor containing one of :data:`_REPO_MARKERS`,
    or ``None`` if none is found within :data:`_MAX_REPO_SEARCH_LEVELS`
    levels -- which is the installed-package case.
    """
    candidate = _PACKAGE_DIR
    for _ in range(_MAX_REPO_SEARCH_LEVELS + 1):
        if any((candidate / marker).exists() for marker in _REPO_MARKERS):
            return candidate
        if candidate.parent == candidate:  # reached the filesystem root
            return None
        candidate = candidate.parent
    return None


def _is_source_checkout() -> bool:
    """True when the package directory sits inside a repository checkout."""
    return _find_repo_root() is not None


def project_root() -> Path:
    """The repository root, or the effective root for an installed copy.

    Honours ``ASTRAEUS_PROJECT_ROOT`` when set.  For an installed package
    with no repository present, falls back to the data root so callers
    always get a writable, deterministic location.
    """
    override = os.environ.get(_PROJECT_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if _is_source_checkout():
        # _find_repo_root() is non-None here by construction.
        return _find_repo_root()  # type: ignore[return-value]

    return _user_data_root()


def _user_data_root() -> Path:
    """XDG-style writable location for an installed, repository-less copy."""
    base = os.environ.get(_XDG_DATA_HOME_ENV, "").strip()
    if base:
        return Path(base).expanduser() / "astraeus"
    return Path(os.path.expanduser("~")) / ".local" / "share" / "astraeus"


def data_root() -> Path:
    """The root under which all generated artifacts are written.

    Never depends on the process CWD.  See module docstring for the
    resolution order.
    """
    override = os.environ.get(_DATA_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if _is_source_checkout():
        # _find_repo_root() is non-None here by construction.
        return _find_repo_root()  # type: ignore[return-value]

    return _user_data_root()


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) idempotently; return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_path(*parts: str) -> Path:
    """Resolve an artifact path under the data root.

    ``artifact_path("logs", "experiments.json")`` yields the same
    location regardless of which directory the process started in.
    Parent directories are created so callers can write directly.
    """
    if not parts:
        raise ValueError("artifact_path() requires at least one path part")
    resolved = data_root().joinpath(*parts)
    if len(parts) > 1:
        ensure_dir(resolved.parent)
    return resolved
