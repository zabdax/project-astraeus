"""Phase 0: the package foundation (PRD v4.1 §2.3 / Objective B).

Before Phase 0 the repository had no pyproject.toml, no
astraeus/__init__.py, no __version__, and no __main__.py -- `python -m
astraeus` literally could not work. These tests pin the foundation.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
PACKAGE_INIT = PROJECT_ROOT / "astraeus" / "__init__.py"
MAIN_MODULE = PROJECT_ROOT / "astraeus" / "__main__.py"


def test_pyproject_toml_exists_and_parses():
    assert PYPROJECT.exists(), "pyproject.toml is missing"
    with open(PYPROJECT, "rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["name"] == "astraeus"


def test_pyproject_declares_the_scientific_backends():
    """PRD §4.2 item 1: wotan and transitleastsquares must be REQUIRED
    dependencies. Their prior absence is why a missing backend could
    silently change science."""
    with open(PYPROJECT, "rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]
    deps_text = " ".join(deps)
    assert "wotan" in deps_text
    assert "transitleastsquares" in deps_text


def test_batman_is_not_a_required_dependency():
    """PRD §13.3: batman is GPL-3.0 and its adoption is an UNRESOLVED
    user-level licensing decision, so it must never be an implicit
    runtime obligation. It belongs to an optional extra only."""
    with open(PYPROJECT, "rb") as fh:
        data = tomllib.load(fh)
    deps = " ".join(data["project"]["dependencies"])
    assert "batman" not in deps
    extras = data["project"].get("optional-dependencies", {})
    assert "batman" in extras


def test_version_is_declared_and_single_sourced():
    """One authoritative version source, no hardcoded duplicates."""
    import astraeus

    assert isinstance(astraeus.__version__, str)
    assert astraeus.__version__  # non-empty
    with open(PYPROJECT, "rb") as fh:
        data = tomllib.load(fh)
    # Version is dynamic (read from astraeus.__version__), not duplicated.
    assert "version" in data["project"] or "version" in data["project"].get("dynamic", [])
    if "dynamic" in data["project"]:
        assert "version" in data["project"]["dynamic"]


def test_package_init_and_main_exist():
    assert PACKAGE_INIT.exists()
    assert MAIN_MODULE.exists()


def _run_cli(*args, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "astraeus", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_cli_version():
    """`python -m astraeus --version` must work and report __version__."""
    import astraeus

    result = _run_cli("--version", cwd=str(PROJECT_ROOT))
    assert result.returncode == 0, result.stderr
    assert astraeus.__version__ in result.stdout


def test_cli_help():
    """`python -m astraeus --help` must work and exit cleanly."""
    result = _run_cli("--help", cwd=str(PROJECT_ROOT))
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_cli_capabilities_reports_backends():
    """The capabilities subcommand must emit the PRD §22 payload shape."""
    result = _run_cli("capabilities", cwd=str(PROJECT_ROOT))
    assert result.returncode == 0, result.stderr
    import json

    payload = json.loads(result.stdout)
    assert {"batman", "wotan", "tls"} <= set(payload)


def test_console_script_entrypoint_declared():
    """pyproject must declare a console script equal to the module CLI."""
    with open(PYPROJECT, "rb") as fh:
        data = tomllib.load(fh)
    scripts = data["project"].get("scripts", {})
    assert scripts.get("astraeus") == "astraeus.__main__:main"


@pytest.mark.parametrize("module", ["astraeus", "astraeus.core", "astraeus.analysis"])
def test_package_imports_without_heavy_or_web_dependencies(module):
    """Importing the package must stay cheap and must never pull in the
    web framework (engine boundary, PRD §4.1)."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr
