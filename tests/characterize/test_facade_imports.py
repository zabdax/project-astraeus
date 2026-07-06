"""The BWC contract: every symbol any of the 23 import sites currently
imports from the 5 in-scope files must still resolve after the refactor.

This is the single most important Phase 1 test. If a refactor drops a
symbol, this file goes red and the engineer MUST add a re-export
before proceeding.
"""
from __future__ import annotations

import importlib
import sys


# Each entry: (importing_module_path, facade_module, symbol)
IMPORT_CONTRACTS = [
    # lightkurve_client importers
    ("astraeus.core.ingestion", "astraeus.core.lightkurve_client", "LightkurveClient"),
    ("tools.diagnostics.ultimate_stress_test", "astraeus.core.lightkurve_client", "LightkurveClient"),

    # nasa_archive importers
    ("astraeus.core.ingestion", "astraeus.core.nasa_archive", "NASAExoplanetArchive"),
    ("tests.test_nasa_archive_network", "astraeus.core.nasa_archive", "NASAExoplanetArchive"),

    # data/loader importers
    ("tests.test_loader", "astraeus.data.loader", "universal_load_lightcurve"),
    ("tests.test_multi_planet_search_real_data", "astraeus.data.loader", "load_nasa_lightcurve"),
    ("tests.test_multi_planet_search_real_data", "astraeus.data.loader", "universal_load_lightcurve"),

    # data/adapter importers
    ("astraeus.data", "astraeus.data.adapter", "DataAdapter"),
    ("astraeus.core.ingestion", "astraeus.data.adapter", "DataAdapter"),
    ("ui.pages.detective", "astraeus.core.ingestion", "DataAdapter"),  # re-export
    ("tests.test_adapter", "astraeus.data.adapter", "DataAdapter"),
]


def test_all_facade_imports_resolve():
    """Every documented import contract still resolves post-refactor."""
    for _caller, facade_module, symbol in IMPORT_CONTRACTS:
        # Skip if the caller's own dependencies aren't installed (we're
        # not testing the caller, only the facade).
        try:
            importlib.import_module(_caller)
        except (ImportError, ModuleNotFoundError):
            pass
        mod = importlib.import_module(facade_module)
        assert hasattr(mod, symbol), (
            f"{facade_module}.{symbol} missing — facade must re-export it. "
            f"Caller {_caller} would break."
        )


def test_no_module_level_underscore_aliases_dropped_from_lightkurve_client():
    """The 17 module-level constants in lightkurve_client.py must remain importable.

    Even unused-by-current-callers constants (orphan _TESS_LC_*) stay on the
    surface because their absence would be an observable behaviour change
    for monkeypatching users.
    """
    from astraeus.core import lightkurve_client as lkc
    expected = [
        "_LIGHTKURVE_CACHE_DIR", "_ASTRAEUS_LIGHTKURVE_CACHE_DIR",
        "_MAX_DOWNLOAD_SEGMENTS", "_MAST_DOWNLOAD_URL",
        "_TESS_READ_TIMEOUT", "_KEPLER_READ_TIMEOUT", "_CONNECT_TIMEOUT",
        "_STREAM_CHUNK_BYTES", "_STREAM_MAX_ATTEMPTS", "_STREAM_BACKOFF_BASE",
        "_S3_PUBLIC_BUCKET", "_S3_TESS_KEY_PREFIX", "_S3_KEPLER_KEY_PREFIX",
        "_TESS_LC_DOWNLOAD_TIMEOUT", "_TESS_LC_MAX_RETRIES", "_TESS_LC_RETRY_BACKOFF",
        "_TARGET_TIC_TABLE",
    ]
    for name in expected:
        assert hasattr(lkc, name), f"lightkurve_client.{name} dropped"
