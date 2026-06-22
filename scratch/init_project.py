"""Create the initial ASTRAEUS project workspace.

The script is intentionally idempotent: directories are created when missing,
and files are only written if they do not already exist.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT / "astraeus"

README_CONTENT = """# ASTRAEUS

ASTRAEUS is a computational astrophysics project focused on first-principles
modeling of exoplanet transit light curves.

## Primary Research Question

How accurately can exoplanet transit parameters be recovered from noisy
photometric data using first-principles modeling?
"""

RESEARCH_LOG_CONTENT = """# ASTRAEUS Research Log

Use this log to track hypotheses, model assumptions, data provenance,
experiments, fitting results, and unresolved questions.
"""

PYTHON_FILE_CONTENT = '"""ASTRAEUS project module."""\n'
INIT_FILE_CONTENT = '"""ASTRAEUS package namespace."""\n'

DIRECTORIES = [
    PACKAGE_ROOT / "core",
    PACKAGE_ROOT / "data",
    PACKAGE_ROOT / "analysis",
    PACKAGE_ROOT / "visualization",
    PACKAGE_ROOT / "notebooks",
    PACKAGE_ROOT / "logs",
]

FILES = {
    ROOT / "README.md": README_CONTENT,
    PACKAGE_ROOT / "main.py": (
        '"""Command-line entry point for ASTRAEUS."""\n\n\n'
        "def main() -> None:\n"
        '    """Run the ASTRAEUS application."""\n'
        '    print("ASTRAEUS workspace initialized.")\n\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"
    ),
    PACKAGE_ROOT / "core" / "__init__.py": INIT_FILE_CONTENT,
    PACKAGE_ROOT / "core" / "orbital_models.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "core" / "transit_model.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "data" / "__init__.py": INIT_FILE_CONTENT,
    PACKAGE_ROOT / "data" / "loader.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "data" / "preprocessing.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "analysis" / "__init__.py": INIT_FILE_CONTENT,
    PACKAGE_ROOT / "analysis" / "fitting.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "analysis" / "error_analysis.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "visualization" / "__init__.py": INIT_FILE_CONTENT,
    PACKAGE_ROOT / "visualization" / "plots.py": PYTHON_FILE_CONTENT,
    PACKAGE_ROOT / "logs" / "research_log.md": RESEARCH_LOG_CONTENT,
}


def create_directories() -> None:
    """Create all ASTRAEUS directories if they are missing."""
    for directory in DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def create_files() -> None:
    """Create scaffold files without overwriting existing content."""
    for path, content in FILES.items():
        if path.exists():
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main() -> None:
    """Build the ASTRAEUS workspace scaffold."""
    create_directories()
    create_files()
    print(f"ASTRAEUS scaffold is ready at {PACKAGE_ROOT}")


if __name__ == "__main__":
    main()
