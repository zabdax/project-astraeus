"""Phase 0: artifact/config paths must not depend on the process CWD.

PRD v4.1 §4.4 / §17. Before Phase 0 the ledger path was hardcoded as
`os.path.join("logs", "experiments.json")` and every artifact directory
was CWD-relative, so a CLI run from `/` wrote artifacts somewhere
unexpected or failed outright.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from astraeus.core import paths
from astraeus.core.paths import artifact_path, data_root, project_root


def test_data_root_is_absolute_and_cwd_independent(tmp_path, monkeypatch):
    """With an explicit data dir, resolution must be absolute regardless
    of where the process happens to be started from."""
    monkeypatch.setenv("ASTRAEUS_DATA_DIR", str(tmp_path / "explicit"))
    monkeypatch.chdir(tmp_path)

    root = data_root()
    assert Path(root).is_absolute()
    assert Path(root) == (tmp_path / "explicit").resolve()


def test_artifact_path_never_relative_to_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRAEUS_DATA_DIR", str(tmp_path / "artifacts"))
    monkeypatch.chdir(tmp_path)

    resolved = artifact_path("logs", "experiments.json")
    assert Path(resolved).is_absolute()
    # It resolves under the data root, not under the (unrelated) CWD.
    assert Path(resolved).is_relative_to((tmp_path / "artifacts").resolve())


def test_artifact_path_creates_parent_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRAEUS_DATA_DIR", str(tmp_path / "newroot"))
    resolved = artifact_path("runs", "nested", "report.json")
    assert Path(resolved).parent.exists()


def test_project_root_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRAEUS_PROJECT_ROOT", str(tmp_path))
    assert Path(project_root()) == tmp_path.resolve()


def test_source_checkout_resolves_in_repo_not_user_data(monkeypatch):
    """Regression guard for the source-checkout branch.

    With no env override, a run from a source checkout must resolve the
    data root to the *repository* root -- not to the package directory
    (one level too shallow) and not to the XDG user dir.

    Before this was fixed, ``_PACKAGE_DIR`` was computed as
    ``Path(__file__).parent.parent`` = ``<repo>/astraeus`` while the repo
    markers live at ``<repo>/``, so ``_is_source_checkout()`` returned
    False even inside a checkout and every developer artifact silently
    landed in ``~/.local/share/astraeus``. That broke consumers reading
    the in-repo ledger (tests/test_experiment_history.py) and quietly
    defeated Objective E for developer runs.
    """
    monkeypatch.delenv("ASTRAEUS_DATA_DIR", raising=False)
    monkeypatch.delenv("ASTRAEUS_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    root = data_root()
    # The resolved root must actually contain this source tree...
    assert Path(paths.__file__).is_relative_to(root)
    # ...and the project marker the resolution claims to detect...
    assert (Path(root) / "pyproject.toml").exists()
    # ...and it must NOT be the XDG user-data fallback.
    xdg_tail = os.path.join(".local", "share", "astraeus")
    assert not str(root).endswith(xdg_tail), (
        f"data_root() fell through to the XDG user dir {root!r} inside a "
        "source checkout; repo-root detection is broken."
    )
    # The same must hold for project_root().
    assert Path(project_root()) == Path(root)


def test_cli_works_from_an_unrelated_directory(tmp_path):
    """The Phase 0 definition of done: `python -m astraeus` must work
    from a directory that has nothing to do with the repository."""
    result = subprocess.run(
        [sys.executable, "-m", "astraeus", "--version"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert "astraeus" in result.stdout


def test_cli_capabilities_from_unrelated_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "astraeus", "capabilities"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert '"tls"' in result.stdout


def test_experiment_ledger_writes_to_data_root_not_cwd(tmp_path, monkeypatch):
    """The historical write path must land in the resolved data root."""
    monkeypatch.setenv("ASTRAEUS_DATA_DIR", str(tmp_path / "ledger-root"))
    monkeypatch.chdir(tmp_path)

    import importlib

    import astraeus.analysis.logging as logging_mod

    importlib.reload(logging_mod)  # re-resolve LOG_FILE under the new root
    try:
        exp_uuid = logging_mod.save_experiment_log(
            params={"target_name": "cwd-probe"},
            metadata={},
            fig_paths=[],
        )
        ledger = Path(logging_mod.LOG_FILE)
        assert ledger.is_absolute()
        assert ledger.is_relative_to((tmp_path / "ledger-root").resolve())
        assert ledger.exists()
        # And the entry is retrievable.
        history = logging_mod.load_experiment_history()
        assert any(e["id"] == exp_uuid for e in history)
    finally:
        # Restore the module-level LOG_FILE for the rest of the suite.
        monkeypatch.delenv("ASTRAEUS_DATA_DIR", raising=False)
        importlib.reload(logging_mod)


def test_paths_module_exposes_a_stable_surface():
    """The resolution mechanism is the single deterministic entry point;
    there is no second, competing path system (PRD §32)."""
    for name in ("project_root", "data_root", "artifact_path", "ensure_dir"):
        assert hasattr(paths, name), f"{name} missing from astraeus.core.paths"
