"""ASTRAEUS contracts -- the frozen, versioned boundaries between subsystems.

Phase 1 introduces this package because the engine's internal boundaries
are currently untyped (PRD v4.1 §5, §6, §8.1).  Before these modules
existed there was no canonical light-curve type: seven different
representations of the same photometry were converted at every boundary,
the dataset identity was ``sha256(metadata)`` (which collides on identical
metadata with different cadences), and the time unit label was dropped at
the ingestion seam.

Every model here is a pydantic v2 model so the FastAPI layer (P1-H) can
generate its OpenAPI schema directly from the contracts, and so a
contract test can assert the wire format by construction.

Ownership (EXECUTION_BUCKETS.md §4):

* :mod:`astraeus.contracts.dataset`     -- P1-A (canonical typed boundary,
  the artifact store, ``ArtifactRef``).
* :mod:`astraeus.contracts.analysis_result` -- P1-B (result schema + alias map).
* :mod:`astraeus.contracts.provenance`  -- P1-C (reproducibility record).

Consumers must treat these as read-only imports; never edit a contract
you do not own (bucket rule in EXECUTION_BUCKETS.md §4).
"""

from astraeus.contracts.dataset import (
    ArtifactRef,
    ArtifactStore,
    Dataset,
    Mission,
    TargetRef,
    TimeUnit,
)
from astraeus.contracts.provenance import Provenance

__all__ = [
    "ArtifactRef",
    "ArtifactStore",
    "Dataset",
    "Mission",
    "Provenance",
    "TargetRef",
    "TimeUnit",
]
