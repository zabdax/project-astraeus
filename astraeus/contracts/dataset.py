"""Canonical typed ``Dataset`` boundary (P1-A).

PRD v4.1 §5 / §8.1.  Before this module there was **no canonical
light-curve type**: seven representations of the same photometry were
converted at every boundary -- dict (in five incompatible key schemas),
bare ``(t, f, e)`` tuple, the dashboard's ``LightCurveData`` dataclass,
``lightkurve.LightCurve``, astropy ``Quantity`` arrays, transient pandas
frames, and ``st.session_state`` dicts.

This module is the one authoritative type that both ingestion stacks
produce and both pipelines consume.  It fixes two measured defects at the
same time:

1. **Identity.**  ``astraeus/analysis/logging.py:generate_dataset_hash``
   hashes ``sha256(metadata)`` -- the same metadata with different
   cadences, array lengths, or entirely different photometry produces the
   *same* hash.  Here identity is a content hash **over the arrays**
   plus ``n_cadence``, ``baseline_days``, mission and sector/quarter
   (PRD §5), following the completeness subsystem's "the hash *is* the
   address" pattern (``simulation/completeness.py:94-97``).
2. **Units.**  ``time_unit`` is produced at exactly two sites
   (``lightkurve_client.py:759,928``) and dropped at the ingestion seam
   (``ingestion.py:242-250`` reconstructs the dict without it; the fusion
   dict never emits it).  The canonical type *carries* the label, and
   conversion to BJD is an explicit, auditable transform rather than an
   assertion by convention (``detection.py:324-329``).

Design rules (PRD §6.2, §8.2):

* JSON wire format.  Arrays are never inlined in a payload that crosses a
  process boundary: they live in the content-addressed artifact store and
  travel as :class:`ArtifactRef` (``{store, path, dtype, shape,
  checksum, n_bytes}``, PRD §5).  Arrow is deferred until a *measured*
  payload justifies it.
* The model is frozen and strict (``extra="forbid"``) so a contract
  violation is a hard error, never a silently-ignored extra key.
* Equality is *identity*, not structural: two ``Dataset`` objects are
  equal iff their content hashes match.  This is why ``__eq__`` /
  ``__hash__`` are overridden -- comparing numpy fields directly would
  return an array and raise on ``bool()``.

This module performs no scientific computation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_core import core_schema

from astraeus.core import paths
from astraeus.core.time_units import bjd_offset_for_mission

__all__ = [
    "TimeUnit",
    "Mission",
    "TargetRef",
    "ArtifactRef",
    "Dataset",
    "ArtifactStore",
    "DATASET_SCHEMA_VERSION",
    "canonical_json",
    "atomic_write_json",
    "atomic_write_bytes",
]

#: Version of this contract.  Bumped only when the *schema* changes in a
#: way that invalidates cached artifacts; recorded in every serialized
#: envelope so a stale artifact is detectable (mirrors
#: ``completeness.py``'s ``schema_version``/``algo_version``).
DATASET_SCHEMA_VERSION = "astraeus.dataset/1"

#: Subdirectory under the data root holding the content-addressed store.
ARTIFACT_STORE_DIR = "artifacts"


# ---------------------------------------------------------------------------
# Canonical serialization primitives (copied from simulation/completeness.py)
# ---------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """Canonical JSON for hashing (the ``completeness.py:89-91`` pattern).

    ``sort_keys=True`` makes the byte stream independent of dict
    construction order; ``default=str`` keeps non-JSON types
    deterministic instead of raising mid-hash.
    """
    return json.dumps(obj, sort_keys=True, default=str)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_sha256(arr: np.ndarray) -> str:
    """SHA256 of a contiguous float64 array's raw bytes.

    ``ascontiguousarray`` first: a non-contiguous view of the same logical
    values has a different byte layout, and identity must not depend on
    how the producer sliced the array.
    """
    return _sha256_bytes(np.ascontiguousarray(arr).tobytes())


def atomic_write_json(path: Path, payload: Any) -> Path:
    """Write ``payload`` as JSON atomically (``completeness.py:232-238``).

    Write to a sibling ``.tmp`` then ``os.replace`` so a reader never
    observes a partially-written artifact and an interrupted write leaves
    no corrupt file at the final path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    """Byte-level twin of :func:`atomic_write_json` (for .npy/.npz)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# pydantic-compatible numpy array type
# ---------------------------------------------------------------------------


def _coerce_float64(value: Any) -> np.ndarray:
    """Coerce list / tuple / ndarray / Quantity-like input to float64 C-order."""
    arr = np.asarray(value)
    if arr.dtype != np.float64:
        arr = arr.astype(np.float64)
    return np.ascontiguousarray(arr)


def _array_to_list(value: np.ndarray) -> list:
    return np.asarray(value).tolist()


class FloatArray:
    """A pydantic field type for ``numpy.ndarray`` of float64.

    Values are plain ``np.ndarray`` at runtime; pydantic only sees this
    shim so that schema generation never touches ``np.ndarray`` directly
    (which pydantic cannot introspect).
    """

    def __class_getitem__(cls, item: Any) -> Any:  # pragma: no cover - typing aid
        return cls

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        return core_schema.no_info_plain_validator_function(
            _coerce_float64,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _array_to_list, when_used="json"
            ),
        )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TimeUnit(str, Enum):
    """Time-system label carried by every :class:`Dataset`.

    The ingestion boundary converts mission units to BJD full before
    construction, so most datasets are ``BJD``.  Raw uploaded files may
    legitimately still be in an offset unit; the label makes that
    *stated* rather than assumed.
    """

    BJD = "BJD"
    BKJD = "BKJD"
    BTJD = "BTJD"
    TJD = "TJD"
    UNKNOWN = "unknown"


class Mission(str, Enum):
    """Photometric mission.  ``K2`` is deliberately absent (PRD §19)."""

    KEPLER = "Kepler"
    TESS = "TESS"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


class TargetRef(BaseModel):
    """A resolved observation target (PRD §5: persistent entity).

    ``resolved_id`` is the survey catalogue identifier (``KIC-11442793`` /
    ``TIC-307210830``); ``name`` is whatever the operator typed.  Archive
    metadata (``pl_name``, ``st_rad``, ``st_teff``, ...) is *reference*
    data attached elsewhere, not part of the dataset's identity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    mission: Mission = Mission.UNKNOWN
    resolved_id: str | None = None
    id_source: str | None = None


# ---------------------------------------------------------------------------
# Artifact reference
# ---------------------------------------------------------------------------


class ArtifactRef(BaseModel):
    """A content-addressed reference to a stored array or document.

    PRD §5: ``{store, path, dtype, shape, checksum, n_bytes}`` -- arrays
    are *never* inlined in a payload that crosses a process or HTTP
    boundary.  ``path`` is relative to the artifact-store root so the same
    record resolves identically on a different mount.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: str
    path: str
    dtype: str
    shape: tuple[int, ...]
    checksum: str
    n_bytes: int
    schema_version: str = DATASET_SCHEMA_VERSION

    def filename(self) -> str:
        return Path(self.path).name


# ---------------------------------------------------------------------------
# The canonical boundary
# ---------------------------------------------------------------------------


class Dataset(BaseModel):
    """The canonical typed light curve.

    Identity = :attr:`content_hash` (SHA256 over the arrays + cadence +
    baseline + mission + sector/quarter).  Two datasets with the same
    arrays and provenance are the *same dataset* even if their metadata
    dicts differ; two datasets with identical metadata but different
    photometry are different datasets.  This is the direct fix for PRD §5
    / §7's "``dataset_hash`` does NOT identify the dataset".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    time: FloatArray
    flux: FloatArray
    flux_err: FloatArray | None = None
    target: TargetRef
    time_unit: TimeUnit = TimeUnit.BJD
    sectors: tuple[int, ...] = ()
    quarter: int | None = None
    source: str = "unknown"

    # Invariants that make the downstream search safe.  Hard failures,
    # not warnings: a mismatched-length or NaN-contaminated array would
    # silently corrupt BLS/TLS statistics.
    @model_validator(mode="after")
    def _validate_arrays(self) -> "Dataset":
        n = len(self.time)
        if n == 0:
            raise ValueError("Dataset.time must be non-empty")
        if len(self.flux) != n:
            raise ValueError(
                f"Dataset.flux length {len(self.flux)} != time length {n}"
            )
        if self.flux_err is not None and len(self.flux_err) != n:
            raise ValueError(
                f"Dataset.flux_err length {len(self.flux_err)} != time length {n}"
            )
        for name, arr in (("time", self.time), ("flux", self.flux)):
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"Dataset.{name} contains non-finite values")
        if self.flux_err is not None:
            if not np.all(np.isfinite(self.flux_err)):
                raise ValueError("Dataset.flux_err contains non-finite values")
            if np.any(self.flux_err < 0.0):
                raise ValueError("Dataset.flux_err must be non-negative")
        if n >= 2 and not np.all(np.diff(self.time) >= 0.0):
            raise ValueError(
                "Dataset.time must be sorted ascending; use Dataset.sorted() "
                "or from_arrays(..., sort=True) to canonicalize"
            )
        return self

    # -- derived identity ---------------------------------------------------

    @property
    def n_cadence(self) -> int:
        """Number of cadences.  Today computed ad hoc at every use site;
        on the contract it is a property of the data."""
        return int(len(self.time))

    @property
    def baseline_days(self) -> float:
        """Temporal span.  Mirrors ``bls_search.py:65``'s ad-hoc
        ``np.max(time) - np.min(time)`` as a first-class attribute."""
        return float(self.time.max() - self.time.min()) if self.n_cadence >= 2 else 0.0

    @property
    def cadence_seconds(self) -> float | None:
        """Median exposure cadence, derived from the time array.

        Kepler long cadence ~1764 s, TESS 20/120 s, short cadence ~59 s.
        ``None`` for a single-cadence dataset.  Measured, never metadata:
        an uploaded file's header can lie, its sampling cannot.
        """
        if self.n_cadence < 2:
            return None
        dt = np.median(np.diff(self.time))
        return float(dt * 86400.0)

    @property
    def is_time_sorted(self) -> bool:
        if self.n_cadence < 2:
            return True
        return bool(np.all(np.diff(self.time) >= 0.0))

    def _identity_payload(self) -> dict:
        """Canonical, platform-stable payload whose hash *is* the dataset."""
        return {
            "contract": DATASET_SCHEMA_VERSION,
            "mission": self.target.mission.value,
            "target_name": self.target.name,
            "resolved_id": self.target.resolved_id,
            "time_unit": self.time_unit.value,
            "sectors": sorted(self.sectors),
            "quarter": self.quarter,
            "n_cadence": self.n_cadence,
            # Full-precision repr: identity must not depend on float
            # formatting choices.  The arrays already hashed below make
            # this redundant in practice, but PRD §5 lists baseline as an
            # identity component, so it is stated explicitly.
            "baseline_days": repr(self.baseline_days),
            "dtype": "float64",
            "time_sha256": _array_sha256(self.time),
            "flux_sha256": _array_sha256(self.flux),
            "flux_err_sha256": _array_sha256(self.flux_err)
            if self.flux_err is not None
            else None,
        }

    @property
    def content_hash(self) -> str:
        """SHA256 over the arrays + identity fields.  THE dataset identity."""
        return _sha256_bytes(canonical_json(self._identity_payload()).encode("utf-8"))

    @property
    def dataset_id(self) -> str:
        """Stable public id: ``ds_<content_hash>``.  Used as a foreign key
        on ``AnalysisResult`` (P1-B) and in the jobs table (P1-E)."""
        return f"ds_{self.content_hash}"

    @property
    def short_id(self) -> str:
        """Truncated id for display-only (logs, UI badges)."""
        return f"ds_{self.content_hash[:12]}"

    # -- equality is identity ------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Dataset):
            return NotImplemented
        return self.dataset_id == other.dataset_id

    def __hash__(self) -> int:
        return hash(self.dataset_id)

    # -- transforms (return NEW datasets; the model is frozen) --------------

    def sorted(self) -> "Dataset":
        """Return a time-sorted copy.  No-op when already sorted."""
        if self.is_time_sorted:
            return self
        order = np.argsort(self.time, kind="stable")
        return self.model_copy(
            update={
                "time": self.time[order],
                "flux": self.flux[order],
                "flux_err": None if self.flux_err is None else self.flux_err[order],
            }
        )

    def to_bjd(self) -> "Dataset":
        """Convert to BJD full using the mission's offset.

        Replaces the implicit convention at ``detection.py:324-329`` with
        an auditable, labelled transform.  Idempotent for BJD input.
        """
        if self.time_unit is TimeUnit.BJD:
            return self
        offset = bjd_offset_for_mission(self.target.mission.value)
        return self.model_copy(
            update={"time": self.time + offset, "time_unit": TimeUnit.BJD}
        )

    def with_flux_err_from_mad(self) -> "Dataset":
        """Attach an *explicitly estimated* per-point error from the flux MAD.

        This replaces the dashboard service's silent
        ``np.zeros_like(flux)`` invention (``dashboard/services/
        data_ingestion.py:46-48``) with a labelled estimate: a zero error
        column would make every chi-square statistic infinite and every
        fit look arbitrarily significant.  Only use when no measured
        error column exists -- the source is recorded as ``mad_estimate``.
        """
        if self.flux_err is not None:
            return self
        mad = float(np.median(np.abs(self.flux - np.median(self.flux))))
        sigma = mad * 1.4826 if mad > 0.0 else 1.0
        return self.model_copy(
            update={"flux_err": np.full(self.n_cadence, sigma), "source": f"{self.source}+mad_estimate"}
        )

    # -- serialization -------------------------------------------------------

    def to_metadata_dict(self) -> dict:
        """Identity + summary, JSON-safe, **arrays excluded**.

        This is the shape that goes into job records, provenance payloads
        and HTTP responses.  Arrays move through the artifact store as an
        :class:`ArtifactRef`.
        """
        return {
            "schema_version": DATASET_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "content_hash": self.content_hash,
            "target": self.target.model_dump(mode="json"),
            "time_unit": self.time_unit.value,
            "n_cadence": self.n_cadence,
            "baseline_days": self.baseline_days,
            "cadence_seconds": self.cadence_seconds,
            "sectors": sorted(self.sectors),
            "quarter": self.quarter,
            "source": self.source,
            "has_flux_err": self.flux_err is not None,
        }

    # -- constructors --------------------------------------------------------

    @classmethod
    def from_arrays(
        cls,
        time: Any,
        flux: Any,
        flux_err: Any | None = None,
        *,
        target: TargetRef | str,
        mission: Mission | str = Mission.UNKNOWN,
        time_unit: TimeUnit | str = TimeUnit.BJD,
        sectors: Sequence[int] = (),
        quarter: int | None = None,
        source: str = "unknown",
        sort: bool = False,
    ) -> "Dataset":
        """Build a Dataset from array-like inputs.

        ``sort=True`` canonicalizes unsorted time (stable argsort); the
        validator otherwise rejects unsorted input rather than silently
        reordering photometry, because BLS/TLS assume monotone time.
        """
        if isinstance(target, str):
            target = TargetRef(name=target, mission=mission)
        if sort:
            # Sort BEFORE validation: the validator rejects unsorted time,
            # so the canonicalization escape hatch must run first.
            order = np.argsort(np.asarray(time), kind="stable")
            time = np.asarray(time)[order]
            flux = np.asarray(flux)[order]
            if flux_err is not None:
                flux_err = np.asarray(flux_err)[order]
        ds = cls(
            time=time,
            flux=flux,
            flux_err=flux_err,
            target=target,
            time_unit=time_unit,
            sectors=tuple(sectors),
            quarter=quarter,
            source=source,
        )
        return ds.sorted() if sort else ds

    @classmethod
    def from_tuple(
        cls, arrays: tuple, *, target: TargetRef | str, **kwargs: Any
    ) -> "Dataset":
        """Adopt the bare ``(t, f, e)`` tuple used throughout
        ``data/loader.py`` (pinned by ``tests/characterize/
        test_data_loader_contract.py``).  A 2-tuple means no error column."""
        if len(arrays) not in (2, 3):
            raise ValueError(
                f"from_tuple expects a (time, flux[, flux_err]) tuple, got {len(arrays)} elements"
            )
        flux_err = arrays[2] if len(arrays) == 3 else None
        return cls.from_arrays(arrays[0], arrays[1], flux_err, target=target, **kwargs)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        target: TargetRef | str | None = None,
        mission: Mission | str = Mission.UNKNOWN,
        time_unit: TimeUnit | str | None = None,
        source: str = "unknown",
        sort: bool = True,
    ) -> "Dataset":
        """Canonicalize any of the five existing dict schemas.

        Accepted shapes (all currently in production):

        * MAST/BJD:      ``{time, flux, flux_err, time_unit, bjd_epoch_offset_applied}``
        * Fusion:        ``{time, flux, flux_err, baseline, kepler_segments, tess_segments}``
        * Ingestion:     ``{status, metadata, time, flux, flux_err, archive_error, ...}``
        * Adapter:       ``{time, flux, flux_err?, metadata}``
        * Orchestrator:  ``{time, flux, target_name, data_source, metadata}`` (no flux_err)

        ``time_unit`` is taken from the dict when present, else from the
        explicit argument, else defaults to BJD -- the seam that
        ``ingestion.py:242-250`` currently drops is restored here.
        """
        if "time" not in data or "flux" not in data:
            raise ValueError("from_dict requires 'time' and 'flux' keys")

        meta = data.get("metadata") or {}

        if target is None:
            name = (
                data.get("target_name")
                or data.get("resolved_target")
                or meta.get("pl_name")
                or meta.get("resolved_target")
                or "Unknown"
            )
            target = TargetRef(name=str(name), mission=mission)
        elif isinstance(target, str):
            target = TargetRef(name=target, mission=mission)

        unit = data.get("time_unit") or time_unit or TimeUnit.BJD

        # Sector/quarter: FITS headers expose them (adapter.py:277-289);
        # nothing else records them today (PRD §7).
        sectors = tuple(sorted(meta.get("sectors", []) or [])) or tuple(
            sorted(data.get("sectors", []) or [])
        )
        quarter = meta.get("quarter", data.get("quarter"))

        return cls.from_arrays(
            data["time"],
            data["flux"],
            data.get("flux_err"),
            target=target,
            time_unit=unit,
            sectors=sectors,
            quarter=quarter,
            source=data.get("data_source", source),
            sort=sort,
        )

    @classmethod
    def from_lightkurve(
        cls, lc: Any, *, target: TargetRef | str, **kwargs: Any
    ) -> "Dataset":
        """Adopt a ``lightkurve.LightCurve`` (``data/loader.py:11`` return type).

        ``lightkurve`` is imported lazily so importing the contract never
        pays for or requires the data-access stack.
        """
        time = np.asarray(lc.time.value, dtype=np.float64)
        flux = np.asarray(lc.flux.value, dtype=np.float64)
        try:
            flux_err = np.asarray(lc.flux_err.value, dtype=np.float64)
        except (AttributeError, ValueError):
            flux_err = None
        return cls.from_arrays(time, flux, flux_err, target=target, **kwargs)

    @classmethod
    def from_light_curve_data(
        cls, lcd: Any, *, target: TargetRef | str, **kwargs: Any
    ) -> "Dataset":
        """Adopt the dashboard's frozen ``LightCurveData`` dataclass
        (``dashboard/services/data_ingestion.py:13``).  Its three fields
        become the canonical arrays; a zero-only error column is treated
        as *absent* so the caller must opt into an estimate explicitly
        (see :meth:`with_flux_err_from_mad`)."""
        flux_err = getattr(lcd, "flux_err", None)
        if flux_err is not None and np.all(np.asarray(flux_err) == 0.0):
            flux_err = None
        return cls.from_arrays(
            lcd.time, lcd.flux, flux_err, target=target, **kwargs
        )


# ---------------------------------------------------------------------------
# Content-addressed artifact store (PRD §8.3)
# ---------------------------------------------------------------------------


class ArtifactStore:
    """Content-addressed store for arrays and JSON documents.

    Copies ``simulation/completeness.py``'s pattern verbatim in spirit:
    the content hash *is* the address (``<root>/<kind>/<hash[:2]>/<hash>``),
    writes are atomic (tmp + ``os.replace``), and every artifact is
    self-describing.  ``Dataset`` arrays, periodogram grids and posterior
    chains all live here; payloads that cross a process or HTTP boundary
    reference them by :class:`ArtifactRef`, never inline (PRD §5, §8.3).
    """

    def __init__(self, root: Path | str | None = None) -> None:
        if root is None:
            root = paths.data_root() / ARTIFACT_STORE_DIR
        self.root = paths.ensure_dir(Path(root))

    # -- path resolution ------------------------------------------------------

    def _sharded(self, kind: str, digest: str, suffix: str) -> Path:
        """``<root>/<kind>/<first 2 hex>/<digest><suffix>``.

        One directory per 256-way shard keeps a large store listable;
        mirrors common content-addressed layouts.
        """
        return self.root / kind / digest[:2] / f"{digest}{suffix}"

    @staticmethod
    def resolve(ref: ArtifactRef, root: Path | str | None = None) -> Path:
        """Absolute path for a reference whose ``path`` is store-relative."""
        base = Path(root) if root is not None else paths.data_root() / ARTIFACT_STORE_DIR
        return (base / ref.path).resolve()

    # -- datasets -------------------------------------------------------------

    def save_dataset(self, ds: Dataset) -> ArtifactRef:
        """Persist a Dataset's arrays as a self-describing ``.npz``.

        Idempotent: the address is the content hash, so re-saving the same
        dataset overwrites byte-identical content.
        """
        digest = ds.content_hash
        path = self._sharded("ds", digest, ".npz")
        if not path.exists():
            buf = _npz_bytes(
                time=ds.time,
                flux=ds.flux,
                flux_err=ds.flux_err if ds.flux_err is not None else np.array([]),
                meta=canonical_json(ds.to_metadata_dict()),
            )
            atomic_write_bytes(path, buf)
        return ArtifactRef(
            store="npz",
            path=str(path.relative_to(self.root)).replace(os.sep, "/"),
            dtype="float64",
            shape=(ds.n_cadence, 3 if ds.flux_err is not None else 2),
            checksum=digest,
            n_bytes=path.stat().st_size,
        )

    def load_dataset(self, ref: ArtifactRef) -> Dataset:
        """Inverse of :meth:`save_dataset`; verifies the hash on load."""
        path = self.resolve(ref, self.root)
        if not path.exists():
            raise FileNotFoundError(f"dataset artifact not found: {path}")
        with np.load(path, allow_pickle=False) as npz:
            meta = json.loads(str(npz["meta"]))
            time = np.asarray(npz["time"], dtype=np.float64)
            flux = np.asarray(npz["flux"], dtype=np.float64)
            raw_err = np.asarray(npz["flux_err"], dtype=np.float64)
            flux_err = raw_err if raw_err.size else None
        ds = Dataset(
            time=time,
            flux=flux,
            flux_err=flux_err,
            target=TargetRef(**meta["target"]),
            time_unit=meta["time_unit"],
            sectors=tuple(meta.get("sectors", [])),
            quarter=meta.get("quarter"),
            source=meta.get("source", "artifact"),
        )
        if ds.content_hash != ref.checksum:
            raise ValueError(
                "dataset artifact content hash mismatch: stored payload does "
                "not match its reference (store is corrupt or was edited)"
            )
        return ds

    # -- raw arrays (periodogram grids, folded curves, chains) -----------------

    def save_array(self, arr: np.ndarray, kind: str = "arr") -> ArtifactRef:
        """Persist a single ndarray as content-addressed ``.npy``."""
        arr = np.ascontiguousarray(arr)
        digest = _sha256_bytes(arr.tobytes())
        path = self._sharded(kind, digest, ".npy")
        if not path.exists():
            atomic_write_bytes(path, arr.tobytes())
        return ArtifactRef(
            store="npy",
            path=str(path.relative_to(self.root)).replace(os.sep, "/"),
            dtype=str(arr.dtype),
            shape=tuple(int(s) for s in arr.shape),
            checksum=digest,
            n_bytes=path.stat().st_size,
        )

    def load_array(self, ref: ArtifactRef) -> np.ndarray:
        path = self.resolve(ref, self.root)
        if not path.exists():
            raise FileNotFoundError(f"array artifact not found: {path}")
        return np.fromfile(path, dtype=np.dtype(ref.dtype)).reshape(ref.shape)

    # -- json documents (provenance, reports, manifests) -----------------------

    def save_json(self, payload: Any, kind: str = "doc") -> ArtifactRef:
        digest = _sha256_bytes(canonical_json(payload).encode("utf-8"))
        path = self._sharded(kind, digest, ".json")
        if not path.exists():
            atomic_write_json(path, payload)
        return ArtifactRef(
            store="json",
            path=str(path.relative_to(self.root)).replace(os.sep, "/"),
            dtype="json",
            shape=(),
            checksum=digest,
            n_bytes=path.stat().st_size,
        )

    def load_json(self, ref: ArtifactRef) -> dict:
        path = self.resolve(ref, self.root)
        if not path.exists():
            raise FileNotFoundError(f"json artifact not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # -- maintenance -----------------------------------------------------------

    def delete_kind(self, kind: str) -> int:
        """Remove every artifact of a kind.  Returns the count removed."""
        base = self.root / kind
        if not base.exists():
            return 0
        removed = 0
        shutil.rmtree(base, ignore_errors=True)
        for dirpath, _dirnames, filenames in os.walk(base):
            removed += len(filenames)
        return removed


def _npz_bytes(**arrays: Any) -> bytes:
    """Serialize arrays to an in-memory ``.npz`` blob (for atomic write)."""
    from io import BytesIO

    buffer = BytesIO()
    np.savez(buffer, **arrays)
    return buffer.getvalue()


def utc_now_iso() -> str:
    """Timezone-aware UTC timestamp (replaces deprecated ``datetime.utcnow()``)."""
    return datetime.now(timezone.utc).isoformat()
