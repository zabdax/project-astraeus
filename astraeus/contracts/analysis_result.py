"""Versioned ``AnalysisResult`` v1 schema + legacy alias map (P1-B).

PRD v4.1 §6.  Today ``detect_transit_candidate`` assembles a ~32-key
untyped dict by sequential ``.update()`` (``detection.py:307-395`` plus
later mutations; 42 keys measured on the full path).  The measured
defects this contract replaces, all verified in the audit:

* **3 period aliases** (``period`` / ``period_days`` / ``orbital_period``)
  plus ``tls_period``, a *different* quantity sharing the namespace;
* **2 candidate flags** (``candidate_found`` / ``is_candidate`` — the same
  object written twice);
* **2 epochs** (``t0`` / ``t0_bjd``);
* **2 depth aliases** and **3 "SNR" semantics** (``snr`` is BLS,
  ``tls_sde`` is a different statistic, ``secondary_eclipse_snr`` a
  third);
* **two confidence scales** — ``confidence_score`` (BLS peak/median,
  unbounded, ~7+) vs ``vetting_confidence`` (0-1);
* **``vetting_status`` in three vocabularies under one key** --
  ``candidate``/``rejected`` (``detection.py:316``), five VettingEngine
  strings, and six cross-vetting strings -- with consumers coupling by
  *string prefix* (``orchestrator.py:179,409``);
* **path-dependent key sets** -- VettingEngine returns 4 keys on
  Insufficient/Inconclusive but 6 on success, so ``delta_chi2_u`` /
  ``delta_chi2_v`` silently vanish;
* **arrays embedded in the payload** -- the ~90k-entry BLS periodogram
  grid rides inside every candidate;
* **no units, no uncertainties, no seed, no version, no config snapshot**;
* **``0.0`` as a "not computable" sentinel** in ``physical_properties``,
  indistinguishable from a genuine zero.

The v1 design rules (PRD §6.2) are applied directly: ``schema_version``
from day one (aligned with the in-repo ``completeness.py`` /
``reporting.py`` convention); canonical scientific names *with units in
the field name*; enums for every verdict; nullable sections for
genuinely-optional stages; artifact references instead of inline arrays;
``tls_outcome`` as an enum never a boolean; and the capability snapshot
made structural.
"""

from __future__ import annotations

import hashlib
import math
from enum import Enum
from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from astraeus.contracts.dataset import (
    ArtifactRef,
    ArtifactStore,
    Dataset,
    canonical_json,
    utc_now_iso,
)
from astraeus.contracts.provenance import Provenance
from astraeus.core.capabilities import TlsOutcome

__all__ = [
    "JobStage",
    "JobStatus",
    "StageOutcome",
    "VettingVerdict",
    "WarningSeverity",
    "StructuredWarning",
    "TlsEvidence",
    "TlsSummary",
    "VettingEvidence",
    "GeometricEvidence",
    "PhysicalProperties",
    "SubtractionProvenance",
    "TtvSummary",
    "CandidateEvidence",
    "PipelineSummary",
    "StageRecord",
    "AnalysisResult",
    "ANALYSIS_RESULT_SCHEMA_VERSION",
    "LEGACY_ALIASES",
    "LEGACY_KEY_TO_CANONICAL",
    "LEGACY_VERDICT_TO_CANONICAL",
    "from_legacy_result_dict",
]

#: Contract version.  Follows the existing in-repo convention
#: (``completeness.py:136``, ``reporting.py:730``) but is namespaced so a
#: reader can distinguish a result envelope from a sweep cell.
ANALYSIS_RESULT_SCHEMA_VERSION = "astraeus.analysis_result/1"

#: The legacy ``vetting_status`` values that are *not* accepted any more.
#: Kept as data so the migration table is self-documenting (PRD §6.4).
_LEGACY_VERDICTS = (
    # detection.py:316 (pre-vetting placeholder)
    "candidate",
    "rejected",
    # VettingEngine.vet_transit_shape (vetting.py:123-141)
    "Insufficient Data",
    "Inconclusive",
    "Indeterminate",
    "Likely Planet",
    "Ambiguous/False Positive",
    # detection.py cross-vetting ladder (462/470/479/494/496/516)
    "Verified Planet Candidate",
    "Eclipsing Binary Detected",
    "V-Shaped False Positive Risk (Potential Grazing Binary)",
    "Verified Planet Candidate (Atmospheric Occultation Detected)",
    "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)",
)


class JobStage(str, Enum):
    """Pipeline stages, named from the real ``detect_transit_candidate``
    call path (PRD §5.1) -- note ``SEARCHING`` (the dominant cost) and
    ``VETTING``, not the generic "DETECTING"/"CROSS_VALIDATING" names."""

    QUEUED = "QUEUED"
    STARTING = "STARTING"
    FETCHING = "FETCHING"
    PREPROCESSING = "PREPROCESSING"
    SEARCHING = "SEARCHING"
    VETTING = "VETTING"
    SUBTRACTING = "SUBTRACTING"
    DERIVING = "DERIVING"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"
    # Terminal states are stages too, so a record can always name where
    # it stopped (PRD §5.1: "FAILED / CANCELLED (terminal, from any stage)").
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStage.COMPLETED, JobStage.FAILED, JobStage.CANCELLED)


class JobStatus(str, Enum):
    """Coarse job lifecycle state (the SQLite jobs table's status column)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    @property
    def is_live(self) -> bool:
        """A live job has a process that may still be running (or was
        orphaned by a crash and must be reclaimed at startup)."""
        return self in (JobStatus.QUEUED, JobStatus.RUNNING)


class StageOutcome(str, Enum):
    """Per-stage result."""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"
    RUNNING = "running"


class VettingVerdict(str, Enum):
    """The single canonical verdict vocabulary.

    Replaces the three overlapping vocabularies that shared the
    ``vetting_status`` key.  Every legacy string maps onto exactly one
    member (see :data:`LEGACY_VERDICT_TO_CANONICAL`), and each member
    carries its own legacy label so a downstream consumer that still
    couples by ``startswith("Verified Planet Candidate")`` keeps working.
    """

    NOT_VETTED = "not_vetted"
    REJECTED = "rejected"
    INSUFFICIENT_DATA = "insufficient_data"
    INCONCLUSIVE = "inconclusive"
    INDETERMINATE = "indeterminate"
    LIKELY_PLANET = "likely_planet"
    AMBIGUOUS_FALSE_POSITIVE = "ambiguous_false_positive"
    VERIFIED_PLANET_CANDIDATE = "verified_planet_candidate"
    VERIFIED_PLANET_CANDIDATE_WITH_SECONDARY = (
        "verified_planet_candidate_with_secondary"
    )
    ECLIPSING_BINARY = "eclipsing_binary"
    ECLIPSING_BINARY_WITH_SECONDARY = "eclipsing_binary_with_secondary"
    GRAZING_BINARY_RISK = "grazing_binary_risk"

    @property
    def legacy_label(self) -> str:
        return _CANONICAL_TO_LEGACY_VERDICT.get(self, self.value)

    @property
    def is_accepted(self) -> bool:
        """Replicates ``orchestrator.py``'s
        ``vetting_status.startswith("Verified Planet Candidate")`` test as a
        property of the enum, so the prefix coupling cannot drift again."""
        return self in (
            VettingVerdict.VERIFIED_PLANET_CANDIDATE,
            VettingVerdict.VERIFIED_PLANET_CANDIDATE_WITH_SECONDARY,
        )

    @property
    def is_binary(self) -> bool:
        return self in (
            VettingVerdict.ECLIPSING_BINARY,
            VettingVerdict.ECLIPSING_BINARY_WITH_SECONDARY,
        )


LEGACY_VERDICT_TO_CANONICAL: dict[str, VettingVerdict] = {
    "candidate": VettingVerdict.NOT_VETTED,
    "rejected": VettingVerdict.REJECTED,
    "Insufficient Data": VettingVerdict.INSUFFICIENT_DATA,
    "Inconclusive": VettingVerdict.INCONCLUSIVE,
    "Indeterminate": VettingVerdict.INDETERMINATE,
    "Likely Planet": VettingVerdict.LIKELY_PLANET,
    "Ambiguous/False Positive": VettingVerdict.AMBIGUOUS_FALSE_POSITIVE,
    "Verified Planet Candidate": VettingVerdict.VERIFIED_PLANET_CANDIDATE,
    "Verified Planet Candidate (Atmospheric Occultation Detected)": (
        VettingVerdict.VERIFIED_PLANET_CANDIDATE_WITH_SECONDARY
    ),
    "Eclipsing Binary Detected": VettingVerdict.ECLIPSING_BINARY,
    "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)": (
        VettingVerdict.ECLIPSING_BINARY_WITH_SECONDARY
    ),
    "V-Shaped False Positive Risk (Potential Grazing Binary)": (
        VettingVerdict.GRAZING_BINARY_RISK
    ),
}

_CANONICAL_TO_LEGACY_VERDICT: dict[VettingVerdict, str] = {
    v: k for k, v in LEGACY_VERDICT_TO_CANONICAL.items()
}


class WarningSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class StructuredWarning(BaseModel):
    """A warning that reached the user, machine-readable (PRD §5).

    Replaces ``print()``-to-inherited-stdout warnings that were never
    linked to a job and could not be replayed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: WarningSeverity = WarningSeverity.WARNING
    stage: JobStage | None = None
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-candidate evidence
# ---------------------------------------------------------------------------


class TlsEvidence(BaseModel):
    """The TLS cross-validation gate, per candidate.

    ``outcome`` is the authoritative four-valued state (PRD §4.2); the
    legacy boolean ``tls_valid`` is derived from it, never the reverse.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: TlsOutcome = TlsOutcome.NOT_ATTEMPTED
    sde: float | None = None
    fap: float | None = None
    period_days: float | None = None
    # |P_tls - P_bls| / P_bls -- the agreement statistic the gate depends on
    period_agreement_fraction: float | None = None
    environment_error: str | None = None
    scientific_error: str | None = None

    @property
    def tls_valid(self) -> bool:
        """Legacy compatibility: only ``ran_pass`` is True."""
        return self.outcome is TlsOutcome.RAN_PASS


class VettingEvidence(BaseModel):
    """Shape diagnostics.  The path-dependent 4-vs-6-key defect becomes
    nullable fields: ``delta_chi2_*`` are ``None`` when the vetting path
    did not compute them, and that is now *stated* rather than *absent*."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: VettingVerdict = VettingVerdict.NOT_VETTED
    confidence: float | None = None
    u_shape_chi2: float | None = None
    v_shape_chi2: float | None = None
    delta_chi2_u: float | None = None
    delta_chi2_v: float | None = None

    @property
    def vetting_status(self) -> str:
        """Legacy key value."""
        return self.verdict.legacy_label

    @property
    def vetting_confidence(self) -> float | None:
        return self.confidence


class GeometricEvidence(BaseModel):
    """Measured geometric quantities + the secondary-eclipse gate.

    ``v_shape_metric`` is the value that actually reaches a consumer.
    The audit found ``geometric_validation.py:22`` hardwires it to ``0.0``
    and ``detection.py:366`` unconditionally overwrites it with
    ``1 - vetting_confidence``; the canonical field records the *live*
    value and :meth:`was_geometric_producer_overridden` states the
    provenance of the number rather than hiding it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    v_shape_metric: float | None = None
    flat_bottom_fraction: float | None = None
    secondary_eclipse_depth_fraction: float | None = None
    secondary_eclipse_snr: float | None = None
    secondary_eclipse_detected: bool = False
    secondary_eclipse_threshold_ppm: float | None = None
    secondary_eclipse_threshold_mode: str | None = None


class PhysicalProperties(BaseModel):
    """Derived physical quantities, with uncertainties where they exist.

    ``physical_properties.py`` uses ``0.0`` as the "not computable"
    sentinel and ``round()``s outputs; the canonical fields are nullable
    and carry the *raw* value, so a genuine zero is distinguishable from
    "not computed".  Uncertainties are absent in v1 (PRD §6.1) and arrive
    with inference in Phase 4 (§6.3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    radius_earth: float | None = None
    equilibrium_temp_k: float | None = None
    jwst_tsm_score: float | None = None
    stellar_radius_solar: float | None = None


class SubtractionProvenance(BaseModel):
    """Which model removed the accepted signal (PRD §4.2 / §13.3).

    ``batman`` and the trapezoid fallback are *scientifically different*
    (zero limb darkening, no curvature); a fallback run must never be
    representable as the preferred backend.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str
    backend_available: bool = True


class TtvSummary(BaseModel):
    """Transit-timing residuals.  Computed today and discarded; persisted
    only when a consumer exists (PRD §19 non-goal: no TTV persistence)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_epochs: int
    rms_minutes: float | None = None
    max_abs_minutes: float | None = None
    artifact: ArtifactRef | None = None


class CandidateEvidence(BaseModel):
    """One candidate: measured evidence + the gate outcome each cleared.

    Never a free-text verdict (PRD §5).  Canonical names carry their
    units (``period_days``, ``duration_hours``, ``depth_fraction``,
    ``epoch_bjd``, ``radius_earth``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    signal_index: int = 0
    iteration: int | None = None

    # --- Canonical scientific quantities -------------------------------
    period_days: float | None = None
    epoch_bjd: float | None = None
    duration_hours: float | None = None
    depth_fraction: float | None = None

    # --- Detection statistics ------------------------------------------
    snr: float | None = None
    bls_confidence: float | None = None  # peak/median power, unbounded

    # --- Sub-stages (nullable = stage did not run, never "zero") -------
    vetting: VettingEvidence = Field(default_factory=VettingEvidence)
    tls: TlsEvidence = Field(default_factory=TlsEvidence)
    geometric: GeometricEvidence = Field(default_factory=GeometricEvidence)
    physical: PhysicalProperties = Field(default_factory=PhysicalProperties)
    subtraction: SubtractionProvenance | None = None

    # --- Arrays are references, never inline (the 90k-entry fix) -------
    periodogram_ref: ArtifactRef | None = None
    folded_light_curve_ref: ArtifactRef | None = None
    ttv: TtvSummary | None = None

    # --- Legacy compatibility (§6.4: dual emission for one release) ----
    @property
    def candidate_found(self) -> bool:
        return True

    @property
    def is_candidate(self) -> bool:
        return self.vetting.verdict.is_accepted

    @property
    def is_accepted(self) -> bool:
        return self.vetting.verdict.is_accepted

    def to_legacy_dict(self) -> dict:
        """Emit the legacy key set for this candidate (§6.4)."""
        period = self.period_days
        depth = self.depth_fraction
        duration_days = self.duration_hours / 24.0 if self.duration_hours is not None else None
        legacy: dict[str, Any] = {
            "candidate_found": self.candidate_found,
            "is_candidate": self.is_candidate,
            "period_days": period,
            "period": period,
            "orbital_period": period,
            "transit_depth": depth,
            "depth": depth,
            "duration": duration_days,
            "t0": self.epoch_bjd,
            "t0_bjd": self.epoch_bjd,
            "time_unit": "BJD",
            "snr": self.snr,
            "confidence_score": self.bls_confidence,
            "vetting_status": self.vetting.vetting_status,
            "vetting_confidence": self.vetting.confidence,
            "u_shape_chi2": self.vetting.u_shape_chi2,
            "v_shape_chi2": self.vetting.v_shape_chi2,
            "delta_chi2_u": self.vetting.delta_chi2_u,
            "delta_chi2_v": self.vetting.delta_chi2_v,
            "v_shape_metric": self.geometric.v_shape_metric,
            "flat_bottom_fraction": self.geometric.flat_bottom_fraction,
            "secondary_eclipse_depth": self.geometric.secondary_eclipse_depth_fraction,
            "secondary_eclipse_snr": self.geometric.secondary_eclipse_snr,
            "secondary_eclipse_detected": self.geometric.secondary_eclipse_detected,
            "secondary_eclipse_threshold_ppm": self.geometric.secondary_eclipse_threshold_ppm,
            "secondary_eclipse_threshold_mode": self.geometric.secondary_eclipse_threshold_mode,
            "planet_radius_earth": self.physical.radius_earth,
            "equilibrium_temp_k": self.physical.equilibrium_temp_k,
            "jwst_tsm_score": self.physical.jwst_tsm_score,
            "stellar_radius": self.physical.stellar_radius_solar,
            "tls_outcome": self.tls.outcome.value,
            "tls_valid": self.tls.tls_valid,
            "tls_sde": self.tls.sde,
            "tls_fap": self.tls.fap,
            "tls_period": self.tls.period_days,
            "tls_environment_error": self.tls.environment_error,
            "tls_scientific_error": self.tls.scientific_error,
        }
        if self.subtraction is not None:
            legacy["subtraction_backend"] = self.subtraction.backend
            legacy["subtraction_backend_available"] = self.subtraction.backend_available
        return legacy


# ---------------------------------------------------------------------------
# Run-level summaries
# ---------------------------------------------------------------------------


class PipelineSummary(BaseModel):
    """What the search as a whole did.  Includes the two provenance values
    the legacy record loses today: ``snr_floor`` (never written to
    ``JOB_REGISTRY``) and ``all_peaks_rejected`` (computed by
    ``bls_search.py:244`` and dropped before the result dict)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_signals: int | None = None
    snr_floor: float | None = None
    n_iterations: int = 0
    n_accepted: int = 0
    n_rejected: int = 0
    n_duplicate_retries: int = 0
    all_peaks_rejected: bool = False
    stellar_rotation_period_days: float | None = None
    detrend_method: str | None = None


class StageRecord(BaseModel):
    """Timing + status of one stage (PRD §5.1's progress model)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: JobStage
    outcome: StageOutcome = StageOutcome.OK
    started_at_iso: str | None = None
    finished_at_iso: str | None = None
    duration_seconds: float | None = None
    iteration: int | None = None
    max_iterations: int | None = None
    detail: str | None = None


class TlsSummary(BaseModel):
    """Run-level TLS roll-up (per-candidate detail lives on each
    ``CandidateEvidence``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempted: bool = False
    n_ran_pass: int = 0
    n_ran_fail: int = 0
    n_env_unavailable: int = 0
    n_not_attempted: int = 0
    environment_error: str | None = None

    @property
    def tls_valid(self) -> bool:
        return self.attempted and self.n_env_unavailable == 0


class AnalysisResult(BaseModel):
    """The versioned result of one job over one dataset (PRD §6).

    One Job consumes one Dataset and produces one ``AnalysisResult``
    (PRD §5); ``dataset_id`` is a foreign key to the canonical contract's
    identity, which is a content hash *over the arrays*.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = ANALYSIS_RESULT_SCHEMA_VERSION
    result_id: str
    job_id: str
    target_id: str
    dataset_id: str

    status: JobStatus = JobStatus.COMPLETED
    stage_outcomes: dict[JobStage, StageRecord] = Field(default_factory=dict)
    stages: list[StageRecord] = Field(default_factory=list)

    candidates: list[CandidateEvidence] = Field(default_factory=list)
    pipeline_summary: PipelineSummary = Field(default_factory=PipelineSummary)
    tls: TlsSummary = Field(default_factory=TlsSummary)
    capability_snapshot: dict[str, Any] = Field(default_factory=dict)

    provenance: Provenance | None = None

    # Inference is explicitly ABSENT in v1 (PRD §6.3): MCMC has never run
    # against a real detected candidate, four concrete wiring gaps block
    # it, and the UI must not represent it as a capability before it
    # exists.  The field is present and null; wiring is Phase 4 work.
    inference: None = None

    warnings: list[StructuredWarning] = Field(default_factory=list)
    created_at_iso: str = Field(default_factory=utc_now_iso)
    error: str | None = None
    error_kind: str | None = None

    @model_validator(mode="after")
    def _validate_consistency(self) -> "AnalysisResult":
        if self.status is JobStatus.COMPLETED and self.error is not None:
            raise ValueError(
                "a COMPLETED result must carry no error; use FAILED with a reason"
            )
        if self.status is JobStatus.FAILED and not self.error:
            raise ValueError("a FAILED result must carry an error reason")
        # The two stage views must not disagree.
        if self.stages and self.stage_outcomes:
            for record in self.stages:
                if record.stage in self.stage_outcomes:
                    if self.stage_outcomes[record.stage].outcome is not record.outcome:
                        raise ValueError(
                            f"stage_outcomes and stages disagree for {record.stage}"
                        )
        return self

    @property
    def n_candidates(self) -> int:
        return len(self.candidates)

    @property
    def n_accepted(self) -> int:
        return sum(1 for c in self.candidates if c.is_accepted)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_legacy_dict(self) -> dict:
        """Emit the legacy key set alongside the canonical one (§6.4).

        Existing consumers (tests, ``runs/``, ``tools/``) keep working for
        one release; the alias map in this module is the documented
        migration table.  Arrays stay out: ``periodogram`` is emitted as
        a reference summary, not a 90k-entry inline grid.
        """
        legacy: dict[str, Any] = {
            "schema_version": 1,
            "result_id": self.result_id,
            "job_id": self.job_id,
            "target": self.target_id,
            "dataset_id": self.dataset_id,
            "status": self.status.value,
            "candidate_found": self.n_accepted > 0,
            "is_candidate": self.n_accepted > 0,
            "tls_valid": self.tls.tls_valid,
            "backends_available": dict(self.capability_snapshot),
            "snr_floor": self.pipeline_summary.snr_floor,
            "max_signals": self.pipeline_summary.max_signals,
            "all_peaks_rejected": self.pipeline_summary.all_peaks_rejected,
            "n_iterations": self.pipeline_summary.n_iterations,
            "candidates": [c.to_legacy_dict() for c in self.candidates],
            "time_unit": "BJD",
            "error": self.error,
        }
        return legacy


# ---------------------------------------------------------------------------
# The alias map (PRD §6.4: documented migration table)
# ---------------------------------------------------------------------------

#: Canonical field -> every legacy key that held the same value.
#: A contract test asserts this stays complete against the measured
#: legacy key universe (42 keys on the full vetting path).
LEGACY_ALIASES: dict[str, list[str]] = {
    # Period: three aliases for one quantity (PRD §6.1 defect 1)
    "period_days": ["period", "period_days", "orbital_period"],
    # Depth: two aliases; a *fraction*, despite the ppm-scaled neighbours
    "depth_fraction": ["depth", "transit_depth"],
    # Epoch: two aliases; only one is BJD-labelled in the legacy payload
    "epoch_bjd": ["t0", "t0_bjd"],
    # Duration: the legacy key is in DAYS, the canonical name is in HOURS.
    # The x24 conversion is applied in the bridge, not in the map.
    "duration_hours": ["duration"],
    # Candidate flag: the same object written under two keys
    "candidate_found": ["candidate_found", "is_candidate"],
    # BLS detection statistics
    "snr": ["snr"],
    "bls_confidence": ["confidence_score"],
    # Vetting
    "vetting_confidence": ["vetting_confidence"],
    "u_shape_chi2": ["u_shape_chi2"],
    "v_shape_chi2": ["v_shape_chi2"],
    "delta_chi2_u": ["delta_chi2_u"],
    "delta_chi2_v": ["delta_chi2_v"],
    "vetting_status": ["vetting_status"],
    # Geometric
    "v_shape_metric": ["v_shape_metric"],
    "flat_bottom_fraction": ["flat_bottom_fraction"],
    "secondary_eclipse_depth_fraction": ["secondary_eclipse_depth"],
    "secondary_eclipse_snr": ["secondary_eclipse_snr"],
    "secondary_eclipse_detected": ["secondary_eclipse_detected"],
    "secondary_eclipse_threshold_ppm": ["secondary_eclipse_threshold_ppm"],
    "secondary_eclipse_threshold_mode": ["secondary_eclipse_threshold_mode"],
    # Physical
    "radius_earth": ["planet_radius_earth"],
    "equilibrium_temp_k": ["equilibrium_temp_k"],
    "jwst_tsm_score": ["jwst_tsm_score"],
    "stellar_radius_solar": ["stellar_radius"],
    # TLS (tls_period is deliberately NOT an alias of period_days: it is a
    # different quantity -- the TLS-fitted period, not the BLS peak)
    "tls_sde": ["tls_sde"],
    "tls_fap": ["tls_fap"],
    "tls_period": ["tls_period"],
    "tls_outcome": ["tls_outcome", "tls_valid"],
    "tls_environment_error": ["tls_environment_error"],
    "tls_scientific_error": ["tls_scientific_error"],
    # Subtraction (orchestrator-stamped, only on accepted candidates)
    "subtraction_backend": ["subtraction_backend"],
    "subtraction_backend_available": ["subtraction_backend_available"],
    # Run-level
    "n_cadence": [],
    "baseline_days": [],
    "detrend_method": ["detrend_method"],
    "stellar_rotation_period_days": ["stellar_rotation_period_days"],
    "ttv_data": ["ttv_data"],
    "periodogram": ["periodogram"],
    "backends_available": ["backends_available"],
}

#: Reverse lookup: legacy key -> canonical field.
LEGACY_KEY_TO_CANONICAL: dict[str, str] = {
    legacy: canonical
    for canonical, legacy_keys in LEGACY_ALIASES.items()
    for legacy in legacy_keys
}

#: Legacy result keys whose canonical home is NOT a result field at all.
#:
#: ``time_unit`` moved to the :class:`Dataset` contract (P1-A): the unit
#: label describes the *data*, and PRD §18 item 4 makes carrying it (rather
#: than asserting it by convention) an explicit deliverable. A result
#: payload no longer restates it -- the ``dataset_id`` foreign key is the
#: authoritative reference.  Listed here so the alias-completeness contract
#: test can account for the whole legacy universe without inventing a
#: result field that should not exist.
LEGACY_KEYS_MOVED_OFF_RESULT: frozenset[str] = frozenset({"time_unit"})

#: The measured legacy key universe (42 keys on the 6-key vetting path,
#: 40 on the 4-key path, +2 on orchestrator-accepted candidates).  The
#: contract test asserts every one is accounted for by the alias map.
LEGACY_KEY_UNIVERSE: frozenset[str] = frozenset(
    {
        "candidate_found", "is_candidate", "period_days", "period", "orbital_period",
        "stellar_rotation_period_days", "transit_depth", "stellar_radius",
        "vetting_status", "confidence_score", "snr", "depth", "duration", "t0",
        "t0_bjd", "time_unit", "periodogram", "tls_fap", "tls_sde", "tls_period",
        "tls_valid", "tls_outcome", "tls_environment_error", "tls_scientific_error",
        "backends_available", "detrend_method", "v_shape_metric",
        "flat_bottom_fraction", "secondary_eclipse_depth", "secondary_eclipse_snr",
        "secondary_eclipse_detected", "vetting_confidence", "u_shape_chi2",
        "v_shape_chi2", "delta_chi2_u", "delta_chi2_v", "planet_radius_earth",
        "equilibrium_temp_k", "jwst_tsm_score", "secondary_eclipse_threshold_ppm",
        "secondary_eclipse_threshold_mode", "ttv_data", "subtraction_backend",
        "subtraction_backend_available",
    }
)


# ---------------------------------------------------------------------------
# Legacy -> canonical bridge
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> float | None:
    """Coerce numpy scalars / strings to float, ``None`` when unavailable.

    The legacy dict carries ``np.float64`` on the TLS-ran path and plain
    ``float`` everywhere else (PRD §6.1 type instability); the canonical
    schema must not encode that accident.
    """
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(value)


def _verdict_from_legacy(status: Any) -> VettingVerdict:
    if status is None:
        return VettingVerdict.NOT_VETTED
    if isinstance(status, VettingVerdict):
        return status
    text = str(status).strip()
    if text in LEGACY_VERDICT_TO_CANONICAL:
        return LEGACY_VERDICT_TO_CANONICAL[text]
    # Unknown vocabulary: record it rather than guessing -- the audit's
    # finding was that free-text verdicts drift; the schema must surface
    # a novel one instead of mapping it to a plausible-looking default.
    return VettingVerdict.INDETERMINATE


def from_legacy_result_dict(
    raw: dict,
    *,
    job_id: str,
    target_id: str | None = None,
    dataset: Dataset | None = None,
    dataset_id: str | None = None,
    result_id: str | None = None,
    store: ArtifactStore | None = None,
    max_signals: int | None = None,
    snr_floor: float | None = None,
    warnings: list[StructuredWarning] | None = None,
    status: JobStatus = JobStatus.COMPLETED,
    error: str | None = None,
    error_kind: str | None = None,
) -> AnalysisResult:
    """Build a canonical ``AnalysisResult`` from today's untyped result dict.

    The bridge the migration runs through (PRD §6.4): it maps every legacy
    key onto its canonical field, resolves the three verdict vocabularies,
    turns the path-dependent 4-vs-6-key shape into nullables, and -- when
    an ``ArtifactStore`` is supplied -- moves the periodogram grid out of
    the payload into a content-addressed reference.

    ``snr_floor`` is passed explicitly because the legacy record does not
    carry it (the very hole P1-C/P1-E close); a caller that knows the
    value supplies it, and the summary states it.
    """
    if not isinstance(raw, dict):
        raise TypeError("from_legacy_result_dict expects the legacy result dict")

    target_id = target_id or raw.get("target_name") or "Unknown"
    dataset_id = dataset_id or (dataset.dataset_id if dataset is not None else "unknown")

    # ---- capability snapshot (already structural in Phase 0) --------------
    backends = raw.get("backends_available") or {}

    # ---- the single candidate the legacy dict describes -------------------
    # The legacy shape is one-candidate-per-call: detect_transit_candidate
    # returns one result; the multi-planet loop collects several.
    tls_outcome_raw = raw.get("tls_outcome")
    try:
        tls_outcome = (
            TlsOutcome(tls_outcome_raw)
            if tls_outcome_raw is not None
            else TlsOutcome.NOT_ATTEMPTED
        )
    except ValueError:
        tls_outcome = TlsOutcome.ENV_UNAVAILABLE

    verdict = _verdict_from_legacy(raw.get("vetting_status"))

    period = _to_float(raw.get("period_days", raw.get("period")))
    depth = _to_float(raw.get("depth", raw.get("transit_depth")))
    duration_days = _to_float(raw.get("duration"))
    duration_hours = duration_days * 24.0 if duration_days is not None else None
    depth_ppm = (depth * 1e6) if depth is not None else None

    # The 0.0 sentinel becomes None: a genuine zero radius/temperature is
    # physically impossible, so "not computable" is the honest reading.
    radius = _to_float(raw.get("planet_radius_earth"))
    teq = _to_float(raw.get("equilibrium_temp_k"))
    tsm = _to_float(raw.get("jwst_tsm_score"))

    geometric = GeometricEvidence(
        v_shape_metric=_to_float(raw.get("v_shape_metric")),
        flat_bottom_fraction=_to_float(raw.get("flat_bottom_fraction")),
        secondary_eclipse_depth_fraction=_to_float(raw.get("secondary_eclipse_depth")),
        secondary_eclipse_snr=_to_float(raw.get("secondary_eclipse_snr")),
        secondary_eclipse_detected=_to_bool(raw.get("secondary_eclipse_detected")),
        secondary_eclipse_threshold_ppm=_to_float(
            raw.get("secondary_eclipse_threshold_ppm")
        ),
        secondary_eclipse_threshold_mode=raw.get("secondary_eclipse_threshold_mode"),
    )

    bridge_warnings: list[StructuredWarning] = list(warnings or [])

    # ---- the periodogram: reference, not inline ---------------------------
    # Computed before construction: the model is frozen, so array fields
    # are set once, at build time.
    periodogram_ref: ArtifactRef | None = None
    periodogram = raw.get("periodogram")
    if isinstance(periodogram, dict) and store is not None:
        periods = np.asarray(periodogram.get("periods", []), dtype=np.float64)
        powers = np.asarray(periodogram.get("powers", []), dtype=np.float64)
        if periods.size and powers.size and periods.size == powers.size:
            grid = np.column_stack([periods, powers])
            periodogram_ref = store.save_array(grid, kind="periodogram")
        elif periods.size != powers.size:
            bridge_warnings.append(
                StructuredWarning(
                    code="PERIODOGRAM_SHAPE_MISMATCH",
                    stage=JobStage.SEARCHING,
                    message=(
                        "legacy periodogram periods/powers length mismatch "
                        f"({periods.size} vs {powers.size}); grid not stored"
                    ),
                )
            )
    elif isinstance(periodogram, dict) and store is None:
        bridge_warnings.append(
            StructuredWarning(
                code="PERIODOGRAM_NOT_PERSISTED",
                stage=JobStage.SEARCHING,
                message=(
                    "periodogram grid omitted from the result payload: no "
                    "artifact store was supplied to from_legacy_result_dict"
                ),
            )
        )

    # ---- TTV ---------------------------------------------------------------
    ttv: TtvSummary | None = None
    ttv_raw = raw.get("ttv_data")
    if isinstance(ttv_raw, list) and ttv_raw:
        residuals = [
            _to_float(item.get("ttv_residual_min"))
            for item in ttv_raw
            if isinstance(item, dict)
        ]
        residuals = [r for r in residuals if r is not None]
        if residuals:
            arr = np.asarray(residuals, dtype=np.float64)
            ttv_ref = store.save_array(arr, kind="ttv") if store is not None else None
            ttv = TtvSummary(
                n_epochs=len(residuals),
                rms_minutes=float(np.sqrt(np.mean(arr**2))),
                max_abs_minutes=float(np.max(np.abs(arr))),
                artifact=ttv_ref,
            )

    candidate = CandidateEvidence(
        candidate_id="c1",
        signal_index=0,
        period_days=period,
        epoch_bjd=_to_float(raw.get("t0_bjd", raw.get("t0"))),
        duration_hours=duration_hours,
        depth_fraction=depth,
        snr=_to_float(raw.get("snr")),
        bls_confidence=_to_float(raw.get("confidence_score")),
        vetting=VettingEvidence(
            verdict=verdict,
            confidence=_to_float(raw.get("vetting_confidence")),
            u_shape_chi2=_to_float(raw.get("u_shape_chi2")),
            v_shape_chi2=_to_float(raw.get("v_shape_chi2")),
            delta_chi2_u=_to_float(raw.get("delta_chi2_u")),
            delta_chi2_v=_to_float(raw.get("delta_chi2_v")),
        ),
        tls=TlsEvidence(
            outcome=tls_outcome,
            sde=_to_float(raw.get("tls_sde")),
            fap=_to_float(raw.get("tls_fap")),
            period_days=_to_float(raw.get("tls_period")),
            environment_error=raw.get("tls_environment_error"),
            scientific_error=raw.get("tls_scientific_error"),
        ),
        geometric=geometric,
        physical=PhysicalProperties(
            radius_earth=None if radius is not None and radius <= 0.0 else radius,
            equilibrium_temp_k=None if teq is not None and teq <= 0.0 else teq,
            jwst_tsm_score=None if tsm is not None and tsm <= 0.0 else tsm,
            stellar_radius_solar=_to_float(raw.get("stellar_radius")),
        ),
        subtraction=(
            SubtractionProvenance(
                backend=raw["subtraction_backend"],
                backend_available=_to_bool(raw.get("subtraction_backend_available")),
            )
            if raw.get("subtraction_backend")
            else None
        ),
        periodogram_ref=periodogram_ref,
        ttv=ttv,
    )

    # ---- run-level roll-up -------------------------------------------------
    tls_summary = TlsSummary(
        attempted=tls_outcome
        in (TlsOutcome.RAN_PASS, TlsOutcome.RAN_FAIL, TlsOutcome.ENV_UNAVAILABLE),
        n_ran_pass=1 if tls_outcome is TlsOutcome.RAN_PASS else 0,
        n_ran_fail=1 if tls_outcome is TlsOutcome.RAN_FAIL else 0,
        n_env_unavailable=1 if tls_outcome is TlsOutcome.ENV_UNAVAILABLE else 0,
        n_not_attempted=1 if tls_outcome is TlsOutcome.NOT_ATTEMPTED else 0,
        environment_error=raw.get("tls_environment_error"),
    )

    summary = PipelineSummary(
        max_signals=max_signals,
        snr_floor=snr_floor,
        n_iterations=1,
        n_accepted=1 if candidate.is_accepted else 0,
        n_rejected=0 if candidate.is_accepted else 1,
        all_peaks_rejected=_to_bool(raw.get("all_peaks_rejected")),
        stellar_rotation_period_days=_to_float(raw.get("stellar_rotation_period_days")),
        detrend_method=raw.get("detrend_method"),
    )

    digest = hashlib.sha256(
        canonical_json(
            {"job_id": job_id, "dataset_id": dataset_id, "raw": sorted(raw.keys())}
        ).encode("utf-8")
    ).hexdigest()

    result = AnalysisResult(
        result_id=result_id or f"res_{digest[:16]}",
        job_id=job_id,
        target_id=target_id,
        dataset_id=dataset_id,
        status=status,
        candidates=[candidate],
        pipeline_summary=summary,
        tls=tls_summary,
        capability_snapshot=backends,
        warnings=bridge_warnings,
        error=error,
        error_kind=error_kind,
    )
    return result


def from_legacy_run(
    candidate_dicts: list[dict],
    *,
    job_id: str,
    target_id: str | None = None,
    dataset: Dataset | None = None,
    dataset_id: str | None = None,
    result_id: str | None = None,
    store: ArtifactStore | None = None,
    max_signals: int | None = None,
    snr_floor: float | None = None,
    n_iterations: int | None = None,
    all_peaks_rejected: bool | None = None,
    warnings: list[StructuredWarning] | None = None,
    status: JobStatus = JobStatus.COMPLETED,
    error: str | None = None,
    error_kind: str | None = None,
    capability_snapshot: dict[str, Any] | None = None,
    examined_tls_outcomes: list[str | Any] | None = None,
) -> AnalysisResult:
    """The run-level bridge: ONE ``AnalysisResult`` for the whole search.

    PRD §5 / §6: one Job consumes one Dataset and produces one
    ``AnalysisResult``, whose ``candidates`` list holds 0..N entries.  The
    legacy machinery produces one dict per accepted candidate and nothing
    at all when the search comes up empty -- which is precisely the case
    the Phase 1 gate cares about ("DONE / 0 candidates" must be
    distinguishable from a broken pipeline).  A clean zero-candidate run
    is therefore a ``COMPLETED`` result with an empty list, never a job
    left in a non-terminal state.

    P2-A: ``examined_tls_outcomes`` carries the TLS outcome of every
    examined peak (accepted or rejected), collected by the worker from the
    loop's ``progress`` events.  Rejected peaks never reach
    ``candidate_dicts``, so without this the run-level ``TlsSummary``
    reads "attempted: False" for a gate that demonstrably executed
    (Kepler-90: BLS P=616d, TLS ``ran_fail``).  These outcomes fold into
    the summary counts only -- no candidate entries are created.
    """
    target_id = target_id or (candidate_dicts[0].get("target_name") if candidate_dicts else "Unknown")
    dataset_id = dataset_id or (dataset.dataset_id if dataset is not None else "unknown")

    collected: list[CandidateEvidence] = []
    run_warnings: list[StructuredWarning] = list(warnings or [])
    capability = capability_snapshot

    for index, raw in enumerate(candidate_dicts):
        single = from_legacy_result_dict(
            raw,
            job_id=job_id,
            target_id=target_id,
            dataset=dataset,
            dataset_id=dataset_id,
            store=store,
            max_signals=max_signals,
            snr_floor=snr_floor,
            warnings=[],  # collect below so each candidate keeps its own
        )
        run_warnings.extend(single.warnings)
        if capability is None:
            capability = single.capability_snapshot
        for candidate in single.candidates:
            collected.append(
                candidate.model_copy(
                    update={
                        "candidate_id": f"c{index + 1}",
                        "signal_index": index,
                    }
                )
            )

    # Roll the TLS outcomes into the run-level summary.  P2-A: rejected
    # peaks never become candidates, so their examined outcomes arrive
    # separately.  When present, the examined list is the complete peak
    # record (every candidate came from an examined peak) and supersedes
    # the candidate-derived list -- appending would double-count accepted
    # peaks.  Unknown values are ignored (defensive: engine strings).
    examined: list[TlsOutcome] = []
    for raw_outcome in examined_tls_outcomes or []:
        try:
            examined.append(
                raw_outcome
                if isinstance(raw_outcome, TlsOutcome)
                else TlsOutcome(str(raw_outcome))
            )
        except ValueError:
            continue
    outcomes = examined if examined else [c.tls.outcome for c in collected]
    tls_summary = TlsSummary(
        attempted=any(
            o is not TlsOutcome.NOT_ATTEMPTED for o in outcomes
        ),
        n_ran_pass=sum(1 for o in outcomes if o is TlsOutcome.RAN_PASS),
        n_ran_fail=sum(1 for o in outcomes if o is TlsOutcome.RAN_FAIL),
        n_env_unavailable=sum(1 for o in outcomes if o is TlsOutcome.ENV_UNAVAILABLE),
        n_not_attempted=sum(1 for o in outcomes if o is TlsOutcome.NOT_ATTEMPTED),
        environment_error=next(
            (c.tls.environment_error for c in collected if c.tls.environment_error),
            None,
        ),
    )

    accepted = [c for c in collected if c.is_accepted]
    summary = PipelineSummary(
        max_signals=max_signals,
        snr_floor=snr_floor,
        n_iterations=n_iterations if n_iterations is not None else len(collected),
        n_accepted=len(accepted),
        n_rejected=len(collected) - len(accepted),
        all_peaks_rejected=bool(
            all_peaks_rejected if all_peaks_rejected is not None else (len(collected) == 0)
        ),
        detrend_method=candidate_dicts[0].get("detrend_method") if candidate_dicts else None,
        stellar_rotation_period_days=next(
            (
                _to_float(d.get("stellar_rotation_period_days"))
                for d in candidate_dicts
                if d.get("stellar_rotation_period_days") is not None
            ),
            None,
        ),
    )

    import hashlib

    digest = hashlib.sha256(
        canonical_json(
            {
                "job_id": job_id,
                "dataset_id": dataset_id,
                "n_candidates": len(collected),
                "periods": [
                    _to_float(d.get("period_days", d.get("period"))) for d in candidate_dicts
                ],
            }
        ).encode("utf-8")
    ).hexdigest()

    return AnalysisResult(
        result_id=result_id or f"res_{digest[:16]}",
        job_id=job_id,
        target_id=target_id,
        dataset_id=dataset_id,
        status=status,
        candidates=collected,
        pipeline_summary=summary,
        tls=tls_summary,
        capability_snapshot=capability or {},
        warnings=run_warnings,
        error=error,
        error_kind=error_kind,
    )
