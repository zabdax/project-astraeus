"""ASTRAEUS -- exoplanet transit detection, vetting, and analysis engine.

Phase 0 established this file as the real package root (PRD v4.1 §2.3:
``astraeus/`` was previously a PEP 420 implicit namespace package,
importable only with the repository root on ``sys.path``, with no
``__version__`` anywhere in production code).

``__version__`` is the SINGLE authoritative version source. ``pyproject.toml``
reads it dynamically (``[tool.setuptools.dynamic] version = {attr =
"astraeus.__version__"}``) so no version is duplicated across files.

This module deliberately imports nothing heavy: importing ``astraeus``
must stay cheap and must never pull in a scientific backend or the web
framework. Submodules import their own dependencies lazily.
"""

__version__ = "0.0.3"

# The engine boundary (PRD v4.1 §4.1): the package must not depend on a
# web framework at import time. Importing ``astraeus`` therefore never
# imports streamlit/fastapi/etc.; capability probing is lazy too.
__all__ = ["__version__"]
