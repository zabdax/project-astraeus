"""Request/response models for the ASTRAEUS API layer (P1-H).

Pydantic models are the *wire contract*.  They are deliberately separate
from the engine's own contracts (``astraeus/contracts/``): an HTTP boundary
must validate and version its own shape independently of the domain model,
and PRD §8.2 keeps the wire JSON-first.

Every request is validated here rather than in the routes, because PRD
§13.1 requires input validation on target IDs before they are routed to
MAST/S3 -- the route's job is to hand a *validated* request to the engine.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "TokenRequest",
    "TokenResponse",
    "InlineDataset",
    "TargetDataset",
    "JobSubmission",
    "JobResponse",
    "ResultResponse",
    "ErrorResponse",
    "JobListResponse",
    "ArtifactRefOut",
    "ArtifactLink",
    "TtvManifest",
    "CandidateArtifactEntry",
    "DatasetManifest",
    "ArtifactManifestResponse",
    "PeriodogramPeak",
    "DatasetSeries",
    "PeriodogramSeries",
    "FoldedSeries",
    "TtvSeries",
]

#: PRD §13.1: target identifiers are routed to MAST/S3, so they must match a
#: conservative allowlist.  Real designations (Kepler-90, TRAPPIST-1,
#: KIC 11442793, WASP-12 b, TOI-700) are all ASCII letters, digits, spaces,
#: hyphens, periods and plus signs.  Anything else -- shell metacharacters,
#: path traversal, newlines -- is rejected before it reaches ingestion.
_TARGET_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-\+]{0,63}$")

#: Mission allowlist.  An unknown mission is a 400, never a silent default
#: to "Kepler" -- the same fail-closed rule as the science gates (§4.2).
_MISSIONS = ("Kepler", "K2", "TESS", "UNKNOWN")


class TokenRequest(BaseModel):
    api_key: str = Field(..., min_length=1, description="The configured API key")


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    owner_id: str
    expires_in: int


class InlineDataset(BaseModel):
    """Arrays supplied directly (offline/test path).

    Flux errors may be absent; the ``Dataset`` contract reads a missing or
    all-zero error column as *absent* rather than trusting it (PRD §5),
    so absence is represented as ``None`` on the wire.
    """

    time: list[float] = Field(..., min_length=10)
    flux: list[float] = Field(..., min_length=10)
    flux_err: list[float] | None = None
    target_name: str = Field(..., min_length=1, max_length=64)

    @field_validator("flux_err")
    @classmethod
    def _consistent_length(cls, value, info):
        if value is None:
            return value
        n = len(info.data.get("time", ()))
        if n and len(value) != n:
            raise ValueError(f"flux_err has {len(value)} points, expected {n}")
        return value


class TargetDataset(BaseModel):
    """Fetch a real light curve through the ingestion seam (P1-D/P1-G)."""

    name: str = Field(..., min_length=1, max_length=64)
    mission: str = "Kepler"

    @field_validator("name")
    @classmethod
    def _validate_target(cls, value: str) -> str:
        if not _TARGET_PATTERN.match(value):
            raise ValueError(
                "target name must be 1-64 ASCII letters, digits, spaces, "
                "hyphens, periods or plus signs"
            )
        return value

    @field_validator("mission")
    @classmethod
    def _validate_mission(cls, value: str) -> str:
        if value not in _MISSIONS:
            raise ValueError(f"mission must be one of {_MISSIONS}")
        return value


class JobSubmission(BaseModel):
    """Submit a search job.

    Exactly one of ``dataset`` (inline arrays) or ``target`` (fetch real
    data) must be supplied -- the PRD's "one Job consumes one Dataset".
    """

    dataset: InlineDataset | None = None
    target: TargetDataset | None = None
    max_signals: int = Field(default=5, ge=1, le=10)
    snr_floor: float = Field(default=7.1, ge=0.0, le=100.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _exactly_one_source(self):
        # Cross-field constraint: enforced here (not in the route) so the
        # error is a single clean 422 with a message, never a half-built job.
        if self.dataset is None and self.target is None:
            raise ValueError(
                "supply either 'dataset' (inline arrays) or 'target' (fetch real data)"
            )
        if self.dataset is not None and self.target is not None:
            raise ValueError("supply either 'dataset' or 'target', not both")
        return self

    @property
    def fetch_real_data(self) -> bool:
        return self.target is not None


class JobResponse(BaseModel):
    """The public job row.  Never leaks filesystem paths."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str
    owner_id: str
    target_name: str
    mission: str | None = None
    status: str
    stage: str
    progress: float
    iteration: int | None = None
    max_iterations: int | None = None
    n_candidates: int | None = None
    result_id: str | None = None
    error: str | None = None
    error_kind: str | None = None
    created_at: str
    updated_at: str


class ResultResponse(BaseModel):
    """An ``AnalysisResult`` with its provenance attached (PRD §5/§7).

    Every API result must carry provenance; omitting it would force the
    client to guess what produced the numbers.
    """

    result: dict[str, Any]
    provenance: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    detail: str
    error_kind: str | None = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    count: int


# -- artifact arrays (3D-evidence program) -----------------------------------
#
# Arrays never cross the wire inline in ``AnalysisResult`` (PRD §5/§8.3);
# these models are the *separate, explicit* download surface for the
# browser: a manifest of what a job holds plus decimated series a chart
# can actually render.  Every payload carries its decimation receipt
# (``n_total``/``n_returned``/``stride``) and an immutable ETag so the
# client can cache by content, never by URL.


class ArtifactRefOut(BaseModel):
    """Public projection of ``contracts.dataset.ArtifactRef``.

    ``path`` is store-relative and informational only: the client must
    use the templated ``url`` from the manifest, never build a path.
    """

    store: str
    path: str
    dtype: str
    shape: list[int]
    checksum: str
    n_bytes: int


class ArtifactLink(BaseModel):
    ref: ArtifactRefOut | None = None
    url: str | None = None


class TtvManifest(BaseModel):
    n_epochs: int | None = None
    rms_minutes: float | None = None
    url: str | None = None


class CandidateArtifactEntry(BaseModel):
    candidate_id: str
    period_days: float | None = None
    periodogram: ArtifactLink = Field(default_factory=ArtifactLink)
    folded: ArtifactLink = Field(default_factory=ArtifactLink)
    ttv: TtvManifest = Field(default_factory=TtvManifest)


class DatasetManifest(BaseModel):
    dataset_id: str | None = None
    ref: ArtifactRefOut | None = None
    url: str | None = None


class ArtifactManifestResponse(BaseModel):
    job_id: str
    dataset: DatasetManifest = Field(default_factory=DatasetManifest)
    candidates: list[CandidateArtifactEntry] = Field(default_factory=list)


class PeriodogramPeak(BaseModel):
    period_days: float
    power: float


class DatasetSeries(BaseModel):
    job_id: str
    dataset_id: str | None = None
    type: Literal["dataset"] = "dataset"
    time_unit: str = "BJD"
    n_total: int
    n_returned: int
    stride: int
    t_min: float | None = None
    t_max: float | None = None
    time: list[float]
    flux: list[float]
    flux_err: list[float] | None = None
    etag: str


class PeriodogramSeries(BaseModel):
    job_id: str
    candidate_id: str
    type: Literal["periodogram"] = "periodogram"
    n_total: int
    n_returned: int
    stride: int
    periods: list[float]
    powers: list[float]
    peak: PeriodogramPeak | None = None


class FoldedSeries(BaseModel):
    job_id: str
    candidate_id: str
    type: Literal["folded"] = "folded"
    period_days: float
    epoch_bjd: float
    bins: int
    n_total: int
    phase: list[float]
    flux: list[float]
    counts: list[int]


class TtvSeries(BaseModel):
    job_id: str
    candidate_id: str
    type: Literal["ttv"] = "ttv"
    n_epochs: int
    rms_minutes: float | None = None
    residuals_min: list[float]
