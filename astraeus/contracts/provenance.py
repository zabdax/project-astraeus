"""Provenance contract (P1-C).

PRD v4.1 §7.  Today **no completed run is reconstructible from its own
record**: the git SHA and package version are absent, the dataset hash
covers metadata instead of arrays, ``snr_floor`` -- the decisive
threshold -- is not even written to ``JOB_REGISTRY``
(``orchestrator.py:582-591``), no seed, no BLAS thread count, no CPU or
OS record, and timestamps exist only in side channels.

This module supplies the missing record.  It is modelled on the one
subsystem that already does this correctly --
``astraeus/simulation/completeness.py`` -- whose frozen validated config,
SHA256-over-canonical-JSON with the hash as the filename, resumable
manifest, ``schema_version``/``algo_version`` and atomic ``tmp`` +
``os.replace`` writes are reused here verbatim in spirit (PRD §15:
"reuse the completeness subsystem's machinery ... do not reinvent it").

The honesty rule (PRD §7, retained from v4): *same seed + same pinned
environment (including BLAS) implies a statistically identical posterior*
-- **not** bit-identical.  This contract records enough to make that
claim checkable; it does not promise bit-comparability across platforms.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from astraeus import __version__ as PACKAGE_VERSION
from astraeus.contracts.dataset import (
    ArtifactRef,
    ArtifactStore,
    Dataset,
    canonical_json,
    utc_now_iso,
)

__all__ = [
    "Provenance",
    "EffectiveConfig",
    "EnvironmentRecord",
    "PackageVersions",
    "ProvenanceScope",
    "capture_provenance",
    "PROVENANCE_SCHEMA_VERSION",
]

#: Contract version.  Bumped when the provenance *shape* changes; older
#: records remain readable because the version is written into them.
PROVENANCE_SCHEMA_VERSION = "astraeus.provenance/1"

#: Distribution names whose exact versions must be recorded (PRD §7).
_TRACKED_PACKAGES = (
    "batman-package",  # distribution name for the `batman` import
    "wotan",
    "transitleastsquares",
    "emcee",
    "numpy",
    "scipy",
    "astropy",
    "lightkurve",
    "streamlit",
)

# Fall-back import-name -> distribution-name pairs used when the primary
# distribution lookup fails (some wheels publish differing names).
_PACKAGE_FALLBACKS = {
    "batman-package": "batman",
}


class ProvenanceScope(str, Enum):
    """How widely a provenance record applies."""

    JOB = "job"
    DATASET = "dataset"
    ANALYSIS = "analysis"


class PackageVersions(BaseModel):
    """Exact versions of every scientific package that touched the result.

    ``None`` means the package is not installed in this environment -- a
    fact, not an error, and exactly what the capability snapshot also
    records.  Recording it here makes a result's backends auditable long
    after the run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    batman: str | None = None
    wotan: str | None = None
    tls: str | None = None
    emcee: str | None = None
    numpy: str | None = None
    scipy: str | None = None
    astropy: str | None = None
    lightkurve: str | None = None
    streamlit: str | None = None

    @classmethod
    def capture(cls) -> "PackageVersions":
        from importlib.metadata import PackageNotFoundError, version

        def _resolve(dist: str) -> str | None:
            for candidate in (dist, _PACKAGE_FALLBACKS.get(dist)):
                try:
                    return version(candidate)
                except PackageNotFoundError:
                    continue
            return None

        fields: dict[str, str | None] = {}
        for dist in _TRACKED_PACKAGES:
            key = "tls" if dist == "transitleastsquares" else dist.replace("-package", "")
            fields[key] = _resolve(dist)
        return cls(**fields)


class EnvironmentRecord(BaseModel):
    """Hardware and numerical-environment facts that change results.

    BLAS thread count matters because multi-threaded linear algebra is a
    *numerical* change, not only a performance one (PRD §17 risk
    register); a result computed on 8 OpenBLAS threads is not identical
    to one computed on 1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    python_version: str
    platform: str
    os_version: str
    cpu_model: str
    cpu_count: int | None
    blas_threads: int | None
    omp_num_threads: str | None
    machine: str

    @classmethod
    def capture(cls) -> "EnvironmentRecord":
        cpu_model = (
            platform.processor()
            or _read_cpu_model()
            or "unknown"
        )
        return cls(
            python_version=platform.python_version(),
            platform=platform.platform(),
            os_version=platform.version(),
            cpu_model=cpu_model,
            cpu_count=os.cpu_count(),
            blas_threads=_detect_blas_threads(),
            omp_num_threads=os.environ.get("OMP_NUM_THREADS"),
            machine=platform.machine(),
        )


def _read_cpu_model() -> str | None:
    """Best-effort CPU model string on Linux (ignored elsewhere)."""
    try:
        model_path = Path("/proc/cpuinfo")
        if model_path.exists():
            for line in model_path.read_text(errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def _detect_blas_threads() -> int | None:
    """Active BLAS/OpenMP thread count.

    Prefers ``threadpoolctl`` (installed with numpy/scipy) because it
    reports the *effective* threadpool of each loaded BLAS, not just the
    environment variable.  Falls back to ``OMP_NUM_THREADS``.
    """
    try:
        from threadpoolctl import threadpool_info  # type: ignore[import-untyped]

        pools = threadpool_info()
        if pools:
            counts = {int(p.get("num_threads", 0)) for p in pools if p.get("num_threads")}
            if counts:
                return max(counts)
    except Exception:  # pragma: no cover - optional dependency
        pass
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        raw = os.environ.get(var, "").strip()
        if raw.isdigit():
            return int(raw)
    return None


class EffectiveConfig(BaseModel):
    """The *resolved* configuration that actually drove the run.

    PRD §7 is explicit: not the config file, but the effective values --
    ``snr_floor`` is the decisive threshold and is not persisted anywhere
    today.  Every field is optional because the unified config system is
    still arriving; the record captures what is knowable now, and a
    missing key means "not applicable to this run", never "defaulted
    silently".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Search / detection thresholds
    snr_floor: float | None = None
    detection_confidence_floor: float | None = None
    max_signals: int | None = None
    max_duplicate_retries: int | None = None
    bls_period_min_days: float | None = None
    bls_period_max_days: float | None = None
    # Detrending (PRD §16.1 item 6: the live window is 0.5-1.5 d)
    detrend_method: str | None = None
    detrend_window_min_days: float | None = None
    detrend_window_max_days: float | None = None
    # TLS gate
    tls_use_threads: int | None = None
    tls_period_epochs: int | None = None
    # Vetting
    vetting_u_vs_v_chi2_delta: float | None = None
    vetting_secondary_eclipse_snr: float | None = None
    # Subtraction (PRD §16.1 item 5)
    subtraction_backend: str | None = None
    subtraction_limb_darkening: tuple[float, float] | None = None
    # Multiprocessing / parallelism (P05-A)
    tls_multiprocessing_unlocked: bool | None = None
    # Anything else the caller resolved, namespaced and explicit
    extras: dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    """The complete reproducibility record for one run (PRD §7).

    Surfaced three ways, per the PRD: stored metadata on the job, a
    downloadable machine-readable ``provenance.json`` (see
    :meth:`save`), and a user-facing details drawer (Phase 3, §11).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = PROVENANCE_SCHEMA_VERSION
    provenance_id: str
    scope: ProvenanceScope = ProvenanceScope.JOB

    # Identity of the code
    pipeline_version: str = PACKAGE_VERSION
    git_sha: str = "unknown"
    git_dirty: bool = False
    git_branch: str | None = None
    lockfile_sha256: str | None = None

    # Identity of the data
    dataset_id: str
    dataset_content_hash: str
    n_cadence: int
    baseline_days: float
    mission: str
    target_name: str
    resolved_target_id: str | None = None
    sectors: tuple[int, ...] = ()
    quarter: int | None = None

    # What the run actually did
    effective_config: EffectiveConfig
    capability_snapshot: dict[str, Any]
    package_versions: PackageVersions
    environment: EnvironmentRecord
    seeds: dict[str, int] = Field(default_factory=dict)

    # When
    started_at_iso: str | None = None
    created_at_iso: str = Field(default_factory=utc_now_iso)
    finished_at_iso: str | None = None

    # What it produced (filled in at completion)
    result_id: str | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()

    @property
    def short_id(self) -> str:
        return f"prov_{self.provenance_id[:12]}"

    def to_dict(self) -> dict:
        """JSON-safe canonical form."""
        return self.model_dump(mode="json")

    def save(self, store: ArtifactStore, kind: str = "provenance") -> ArtifactRef:
        """Atomically write ``provenance.json`` into the artifact store.

        The content hash *is* the address (``completeness.py`` pattern),
        so an identical provenance record is written once and referenced
        everywhere it is needed.
        """
        return store.save_json(self.to_dict(), kind=kind)

    @classmethod
    def load(cls, store: ArtifactStore, ref: ArtifactRef) -> "Provenance":
        payload = store.load_json(ref)
        return cls.model_validate(payload)


def capture_git_state(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Best-effort git provenance; never raises (a missing git is a fact).

    Returns ``{git_sha, git_dirty, git_branch}``.  Called from the repo
    root when available so a source checkout reports its own SHA; an
    installed wheel reports ``unknown`` honestly rather than inventing one.
    """
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    if not (root / ".git").exists() and not _git_dir_at(root):
        return {"git_sha": "unknown", "git_dirty": False, "git_branch": None}

    def _git(*args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    sha = _git("rev-parse", "HEAD")
    if sha is None:
        return {"git_sha": "unknown", "git_dirty": False, "git_branch": None}
    return {
        "git_sha": sha,
        "git_dirty": bool(_git("status", "--porcelain")),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
    }


def _git_dir_at(root: Path) -> bool:
    """A ``.git`` file (worktree) also counts."""
    git_path = root / ".git"
    return git_path.is_file()


def _default_repo_root() -> Path:
    from astraeus.core import paths as _paths

    try:
        return _paths.project_root()
    except Exception:  # pragma: no cover - defensive
        return Path.cwd()


def _lockfile_hash() -> str | None:
    """SHA256 of the lockfile if one is present (uv.lock / requirements.txt).

    A lockfile pin is what makes "same pinned environment" checkable; the
    hash (not the contents) is what belongs in the record.
    """
    from astraeus.core import paths as _paths

    root = _paths.project_root()
    for name in ("uv.lock", "requirements.txt"):
        candidate = root / name
        if candidate.is_file():
            return hashlib.sha256(candidate.read_bytes()).hexdigest()
    return None


def capture_provenance(
    dataset: Dataset,
    *,
    effective_config: EffectiveConfig | None = None,
    capability_snapshot: dict[str, Any] | None = None,
    seeds: dict[str, int] | None = None,
    started_at_iso: str | None = None,
    provenance_id: str | None = None,
    repo_root: Path | str | None = None,
    scope: ProvenanceScope = ProvenanceScope.JOB,
) -> Provenance:
    """Assemble a provenance record for a run over ``dataset``.

    This is the single entry point the engine and API layer use; it
    captures the environment once and binds it to a dataset's identity.
    """

    def _short(digest: str, prefix: str) -> str:
        return f"{prefix}_{hashlib.sha256(digest.encode('utf-8')).hexdigest()[:16]}"

    git = capture_git_state(repo_root)
    cap = capability_snapshot
    if cap is None:
        # Lazy: never import heavy backends just to record their absence.
        from astraeus.core.capabilities import capability_snapshot as _snap

        cap = _snap().to_dict()

    pid = provenance_id or _short(
        f"{dataset.dataset_id}:{git['git_sha']}:{canonical_json(effective_config.model_dump() if effective_config else {})}",
        "prov",
    )

    return Provenance(
        provenance_id=pid,
        scope=scope,
        git_sha=git["git_sha"],
        git_dirty=git["git_dirty"],
        git_branch=git["git_branch"],
        lockfile_sha256=_lockfile_hash(),
        dataset_id=dataset.dataset_id,
        dataset_content_hash=dataset.content_hash,
        n_cadence=dataset.n_cadence,
        baseline_days=dataset.baseline_days,
        mission=dataset.target.mission.value,
        target_name=dataset.target.name,
        resolved_target_id=dataset.target.resolved_id,
        sectors=tuple(sorted(dataset.sectors)),
        quarter=dataset.quarter,
        effective_config=effective_config or EffectiveConfig(),
        capability_snapshot=cap,
        package_versions=PackageVersions.capture(),
        environment=EnvironmentRecord.capture(),
        seeds=dict(seeds or {}),
        started_at_iso=started_at_iso,
    )


def provenance_from_result_dict(dataset: Dataset, raw_result: dict, **kwargs: Any) -> Provenance:
    """Best-effort provenance for the legacy (pre-contract) result dict.

    Bridges the gap until the engine emits ``AnalysisResult`` natively
    (P1-B's adoption is incremental): it lifts the config values that
    today's dict *does* carry and marks the rest absent rather than
    inventing them.
    """
    cfg = EffectiveConfig(
        snr_floor=_as_float(raw_result.get("snr_floor")),
        max_signals=_as_int(raw_result.get("max_signals")),
        detrend_method=raw_result.get("detrend_method"),
        subtraction_backend=raw_result.get("subtraction_backend"),
        extras={
            k: v
            for k, v in raw_result.items()
            if k in ("tls_use_threads", "max_duplicate_retries") and v is not None
        },
    )
    return capture_provenance(dataset, effective_config=cfg, **kwargs)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def write_provenance_json(record: Provenance, out_path: Path | str) -> Path:
    """Write a standalone, human-readable ``provenance.json`` file.

    Atomic (tmp + ``os.replace``) and canonical (sorted keys) so two
    records over the same inputs byte-compare on one platform.
    """
    from astraeus.contracts.dataset import atomic_write_json

    return atomic_write_json(Path(out_path), record.to_dict())


def canonical_provenance_json(record: Provenance) -> str:
    """Canonical JSON text of a record (for hashing / byte comparison)."""
    return canonical_json(record.to_dict())
