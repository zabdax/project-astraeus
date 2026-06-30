"""Lightkurve row seam — LightkurveRowPort + a narrow public surface.

Phase 0 of the data-ingestion SOLID/SRP refactor (see
``docs/superpowers/specs/2026-06-30-data-ingestion-solid-refactor-design.md``
section "Network Intercept Layer" and Phase 0, step 0.3) lands this
seam without rewiring any production caller.

Why a *narrow* port (ISP compliance)
------------------------------------
The full ``lightkurve`` ``SearchResult`` / ``LightCurveFile`` API has
dozens of methods. Most of them (``plot``, ``normalize``,
``to_pandas``, ``remove_nans``, ...) are downstream concerns that
should never be exercised by the ingestion collaborators. The spec
intentionally restricts ``LightkurveRowPort`` to three operations:

* ``row.download()`` — the only method that triggers network I/O.
* ``row.products`` — read-only metadata used for caching decisions.
* ``search_result.__iter__`` — row iteration.

Any collaborator that needs more (``search_result.download_all()``,
``len(search_result)``, etc.) widens the port in Phase 2 with a new
Protocol rather than expanding this one.

Spec surface vs. real usage
---------------------------
The current ``lightkurve_client`` module also relies on
``search_result.download_all()`` and ``len(search_result)``. Phase 0
lands the spec-literal surface; ``MastStreamer`` and
``LightCurveDownloader`` (Phase 2.6 / Phase 3.1) widen the port or
introduce a sibling protocol for the broader surface as they extract
that behaviour. Keeping the gap explicit here so the writing-plans
skill captures it as a Phase 2 task.

The matching test double (``FakeLightkurveRow``, ``FakeSearchResult``)
lives at ``tests/_fixtures/fakes.py``, not here, per the strict-mode
decision to keep production code free of test-only artifacts.
"""

from __future__ import annotations

from typing import Any, Protocol


class LightkurveRowPort(Protocol):
    """Contract for a single ``lightkurve`` row's network-touching surface."""

    def download(self) -> Any:
        """Trigger the network download for this row.

        Returns whatever the production ``lightkurve.SearchResult`` /
        row returns today (typically a ``LightCurve`` or ``LightCurveFile``
        collection). Collaborators treat the return value as opaque;
        they only care that side effects (cache population, disk write)
        happened.
        """

        ...

    @property
    def products(self) -> list[Any]:
        """Read-only metadata list of products contained in this row.

        Used by ``DownloadCache`` to construct cache filenames.
        """
        ...