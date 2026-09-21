"""Real-data ingestion bridge into the worker (P1-G).

PRD v4.1 §18 item 1: **real data has never crossed the async subprocess
boundary.**  ``submit_multi_planet_search`` (``orchestrator.py:658``)
receives an already-built dict, and the only live caller of the async
path builds a *synthetic* one -- so the worker subprocess has never seen
a real light curve.

This module is the wiring: it calls the existing ingestion stack
(``core/ingestion.py``'s TTL-cached facade, proven against 13 real
targets from the local FITS cache) and funnels the result through the
canonical :class:`Dataset` contract, which persists it to the artifact
store and returns a content-addressed reference.  The worker then runs
the real pipeline on real arrays (PRD §18: "must use REAL astronomical
data ... no synthetic demo curves").

Nothing here reimplements ingestion; it consolidates it onto the seam
(P1-D) and makes the arrays addressable.
"""

from __future__ import annotations

from typing import Any

from astraeus.contracts.dataset import ArtifactRef, ArtifactStore, Dataset, Mission, TargetRef, TimeUnit

__all__ = ["fetch_real_dataset", "fetch_and_store"]


def _mission(mission: str | None) -> Mission:
    try:
        return Mission(mission) if mission else Mission.UNKNOWN
    except ValueError:
        return Mission.UNKNOWN


def fetch_real_dataset(
    target_name: str,
    *,
    mission: str = "Kepler",
    store: ArtifactStore | None = None,
) -> Dataset:
    """Fetch a real light curve and canonicalize it onto the seam.

    Raises ``RuntimeError`` with the stack's own reason when the fetch
    fails -- an ingestion failure is a FAILED job with a cause, never a
    silent empty dataset (PRD §5.1 / §18).
    """
    from astraeus.core.ingestion import RemoteDiscoveryEngine

    payload: dict[str, Any] = RemoteDiscoveryEngine.fetch_data(target_name, mission)

    status = payload.get("status")
    if status != "success":
        reason = payload.get("reason") or payload.get("archive_error") or status
        raise RuntimeError(
            f"ingestion failed for {target_name!r} ({mission}): {reason}"
        )

    meta = payload.get("metadata") or {}
    target = TargetRef(
        name=str(meta.get("pl_name") or target_name),
        mission=_mission(mission),
        resolved_id=str(meta.get("resolved_target") or target_name),
        id_source="nasa_archive+lightkurve",
    )

    # ``time_unit`` is produced at lightkurve_client.py:759/928 and dropped
    # at ingestion.py:242-250; P1-D restores the forwarding, and the
    # canonical type carries the label from here on (PRD §18 item 4).
    unit = payload.get("time_unit") or "BJD"

    dataset = Dataset.from_dict(
        {
            "time": payload["time"],
            "flux": payload["flux"],
            "flux_err": payload.get("flux_err"),
            "metadata": meta,
        },
        target=target,
        mission=_mission(mission),
        time_unit=unit,
        source="real:ingestion",
        sort=True,
    )
    if dataset.time_unit is not TimeUnit.BJD:
        dataset = dataset.to_bjd()

    if store is not None:
        store.save_dataset(dataset)
    return dataset


def fetch_and_store(
    target_name: str, *, mission: str = "Kepler", store: ArtifactStore
) -> tuple[Dataset, ArtifactRef]:
    """Fetch and persist; returns the dataset and its store reference."""
    dataset = fetch_real_dataset(target_name, mission=mission, store=store)
    return dataset, store.save_dataset(dataset)
