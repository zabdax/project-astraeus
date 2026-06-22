"""Data loading and preprocessing utilities for ASTRAEUS."""

from astraeus.data.preprocessing import inject_gaussian_noise
from astraeus.data.adapter import DataAdapter

# NOTE (Bucket 1, 2026-06-22): the astroquery-based RemoteDiscoveryEngine that
# lived in astraeus/data/discovery.py was DEPRECATED and moved to
# deprecated/astraeus_data_discovery/. It had no live importer; the live
# ingestion path is astraeus.core.ingestion.RemoteDiscoveryEngine. Its package
# re-export is intentionally NOT restored here to avoid resurrecting the
# name collision with core.ingestion.RemoteDiscoveryEngine. See
# reports/bucket1_orphan_investigation.md §2.

__all__ = ["inject_gaussian_noise", "DataAdapter"]
