"""Network seam for the data-ingestion collaborators.

This package owns the *interfaces* that production code depends on for
external I/O. Phase 0 of the data-ingestion SOLID/SRP refactor lands
the seams here without rewiring any production caller. Subsequent
phases plug ``MastStreamer``, ``S3FallbackDownloader``, ``TapClient``,
and ``PsCompanion`` onto ``HttpClientPort``.

See ``docs/superpowers/specs/2026-06-30-data-ingestion-solid-refactor-design.md``
section 3.2 / Phase 0 step 0.1 for the design.
"""