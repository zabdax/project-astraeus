"""The FastAPI + JWT API layer (P1-H).

PRD v4.1 §13.1 requires authentication for public v1 and §5.1 defines the
job model this layer exposes.  This package is the HTTP boundary over the
Phase 1 job system; it owns no scientific logic (PRD §4.1: the engine
contract is invariant under the caller).

Depends on: P1-B (``AnalysisResult``), P1-C (``Provenance``), P1-E
(``JobStore``).  Consumed by: P2-A (vertical slice backend), P3-C
(Analyses route), P3-G (Copilot SSE).

Run with::

    astraeus-api   # or: python -m astraeus.api.main

or compose ``create_app`` inside another ASGI host.
"""

from astraeus.api.main import MAX_REQUEST_BYTES, create_app

__all__ = ["create_app", "MAX_REQUEST_BYTES"]
