# Data Ingestion Layer — SOLID/SRP Refactor — Design

**Date:** 2026-06-30
**Status:** Draft (pending user review)
**Author:** Zubayer Hasan Shaad (via ZCode / brainstorming skill)
**Branch:** v.0.0.2
**Subsystem:** 1 of N (data ingestion → analysis → simulation → dashboard, future specs)

## Motivation

Project Astraeus has grown to ~57 Python source files spanning analysis, core
physics, data, dashboard, simulation, visualization, and workflows. The
CodeGenome knowledge graph identifies the worst SRP offenders (god-nodes) as:

| File | Score | Lines |
|---|---|---|
| `tools/diagnostics/ultimate_stress_test.py` | 152 | (out of scope) |
| `ui/pages/detective.py:render` | 72 | (out of scope) |
| `ui/pages/simulator.py:render` | 65 | (out of scope) |
| `astraeus/core/lightkurve_client.py` | **35** | **917** |
| `astraeus/simulation/completeness.py` | 31 | 526 |
| `astraeus/dashboard/figures.py` | 25 | 725 |
| `astraeus/workflows/pipeline.py` | 24 | 258 |

A full-codebase SOLID refactor in a single spec is too large to design
without losing focus or producing vague sections. The brainstorming skill
recommends decomposition into independent sub-projects, each with its own
spec → plan → implementation cycle.

**This spec covers Subsystem 1: the data ingestion layer.**

The data ingestion layer is the right starting point because:

- It contains the worst god-file in the in-scope surface
  (`lightkurve_client.py` at 917 lines, 19 methods, god-node score 35).
- It is a *leaf* in the dependency graph (no upstream deps within the
  package), so refactoring it does not require concurrent changes
  elsewhere.
- Every higher layer (analysis, workflows, dashboard, simulation, app,
  runs) depends on it. Stabilizing it unblocks future specs.
- The current code carries hard-won reliability patches (FIX 2.3 TESS
  timeout, MAST cache-staging trick, S3 anonymous fallback, curated
  target table) that must be preserved exactly — these constraints
  sharpen the design.

## Scope (in scope)

The 5 files that own data ingestion end-to-end:

1. `astraeus/core/lightkurve_client.py` — MAST download, S3 fallback,
   caching, target resolution, FITS validation, fusion.
2. `astraeus/core/nasa_archive.py` — NASA Exoplanet Archive TAP queries,
   metadata normalization, PS companion fetches.
3. `astraeus/core/ingestion.py` — IngestionController orchestrating the
   above; module-level `_cached_fetch_data`.
4. `astraeus/data/loader.py` — DataFactory + strategy hierarchy
   (NASAArchiveLoader, CSVLoader, JSONLoader) + module-level helpers
   (`fetch_lightcurve`, `clean_lightcurve`, `extract_lightcurve_arrays`,
   `load_nasa_lightcurve`, `universal_load_lightcurve`).
5. `astraeus/data/adapter.py` — DataAdapter for CSV/JSON/FITS parsing.

23 import sites depend on these 5 files. **None of those callers will
be modified.** The refactor is internal-only.

## Scope (explicitly out of scope)

Future specs cover these — not touched here:

- `astraeus/analysis/*` — depends on ingestion; uses facades unchanged.
- `astraeus/dashboard/services/data_ingestion.py` — uses facades.
- `astraeus/workflows/pipeline.py`, `astraeus/core/orchestrator.py`.
- `astraeus/simulation/completeness.py`, `astraeus/simulation/synthetic.py`.
- `astraeus/dashboard/figures.py`, `astraeus/dashboard/ui/*`.
- `app.py`, `ui/pages/*`, `runs/kepler90_blind_search.py`.
- `scripts/qa_runner.py`, `scripts/qa_runner_v2.py`.
- All tests in `tests/`.
- `tools/diagnostics/*`, `deprecated/*`, `scratch/*`.

## Constraints (locked in with the user)

1. **Tight scope.** Only the 5 files above are modified. No caller
   changes.
2. **Backward-compatible public API.** Class names, method names,
   method signatures, return shapes, and module-level constants remain
   exactly as today. Verified by 23 import sites.
3. **Characterize-then-refactor.** Existing behavior is captured in
   regression tests *before* any code moves. The characterization
   suite runs offline via fake HTTP/filesystem/clock/lightkurve.
4. **Network calls behind interfaces.** Production code calls
   `HttpClientPort`; tests inject `FakeHttpClient`. Same pattern for
   filesystem (`FsPort`) and clock (`ClockPort`).
5. **Reliability patches preserved exactly.** Every constant value,
   every `### RELIABILITY:` comment trail, and every algorithmic
   invariant (e.g. `np.float64` precision guard) survives the refactor
   byte-identically.
6. **Classmethods + module-level singleton** for `NASAExoplanetArchive`
   (it has no instance API today).

## Approach (chosen)

**A. "Extract Collaborators"** — the 5 in-scope files become thin
public facades over a set of small, single-responsibility collaborator
classes. Public API frozen; internals rewired through composition.

### Why not B (Service Layer + Protocol Boundaries)

Approach B introduces Protocol-based interfaces throughout and constructor
DI across all collaborators. Cleaner DIP, but bigger churn and a more
invasive change for callers. We chose A because it satisfies the SOLID
goal (small focused classes, dependency injection where needed,
replaceable implementations) without forcing a DI rewrite at every call
site.

### Why not C (Helper functions module)

Approach C extracts module-level helpers. Doesn't really fix SRP — it
just moves god-code. Not a SOLID refactor.

## Architecture (post-refactor package layout)

```
astraeus/
├── core/
│   ├── lightkurve_client.py           # FACADE — thin orchestrator
│   ├── nasa_archive.py                # FACADE — classmethods over singleton
│   ├── ingestion.py                   # FACADE — class + module-level shim
│   └── clients/                       # NEW package: lightkurve collaborators
│       ├── __init__.py
│       ├── _net.py                    # HttpClientPort, HttpResponse,
│       │                              # RequestsHttpClient, FakeHttpClient
│       ├── _fs.py                     # FsPort + RealFs + FakeFs
│       ├── _clock.py                  # ClockPort + RealClock + FakeClock
│       ├── lightkurve_row.py          # LightkurveRowPort + FakeLightkurveRow
│       ├── precision.py               # PrecisionGuard (np.float64 invariant)
│       ├── target_resolver.py         # TargetResolver + _TARGET_TIC_TABLE
│       ├── cache_manager.py           # CacheManager
│       ├── timeout_runner.py          # TimeoutRunner
│       ├── mast_streamer.py           # MastStreamer + MastStreamerConfig
│       ├── s3_fallback.py             # S3FallbackDownloader
│       ├── fits_validator.py          # FitsValidator
│       ├── download_cache.py          # DownloadCache
│       ├── search_prioritizer.py      # SearchPrioritizer
│       ├── lightcurve_downloader.py   # LightCurveDownloader (TESS/Kepler branch)
│       └── fusion_builder.py          # FusionBuilder (cross-mission fusion)
│
│   └── archive/                       # NEW package: NASA archive collaborators
│       ├── __init__.py
│       ├── tap_client.py              # TapClient
│       ├── metadata_normalizer.py     # MetadataNormalizer
│       ├── ps_companion.py            # PsCompanion
│       └── response_parser.py         # ResponseParser
│
│   └── ingestion/                     # NEW package: ingestion collaborators
│       ├── __init__.py
│       ├── mission_resolver.py        # MissionResolver
│       ├── bridge_builder.py          # BridgeBuilder
│       └── fetch_cache.py             # FetchCache (lru_cache wrapper)
│
└── data/
    ├── loader.py                      # FACADE — DataFactory + module fns
    ├── adapter.py                     # FACADE — DataAdapter
    ├── loaders/                       # NEW package: loader strategies
    │   ├── __init__.py
    │   ├── base.py                    # DataLoaderStrategy ABC
    │   ├── nasa_loader.py             # NASAArchiveLoader
    │   ├── csv_loader.py              # CSVLoader
    │   └── json_loader.py             # JSONLoader
    └── adapters/                      # NEW package: parsing collaborators
        ├── __init__.py
        ├── csv_parser.py              # _parse_csv
        ├── json_parser.py             # _parse_json
        ├── fits_parser.py             # _parse_fits + _extract_fits_metadata
        ├── column_scanner.py          # _scan_columns + _resolve_columns
        ├── array_standardizer.py      # _standardize_arrays
        └── adapter_cache.py           # _preserve_in_streamlit
```

## Collaborator class responsibilities

### `astraeus/core/clients/` (11 collaborators + 3 seams)

| Collaborator | Source it owns | Public methods | Constants |
|---|---|---|---|
| `PrecisionGuard` | np.float64 invariant | `enforce(arr)`, `is_safe(arr)` | — |
| `TargetResolver` | `_resolve_target_to_tic` | `resolve(target_name) -> str` | `_TARGET_TIC_TABLE` |
| `CacheManager` | cache dir management | `wipe_global()`, `wipe_dir(path)`, `cache_dir()` | `_LIGHTKURVE_CACHE_DIR`, `_ASTRAEUS_LIGHTKURVE_CACHE_DIR` |
| `TimeoutRunner` | `_call_with_timeout` | `run(fn, *args, timeout, label, **kwargs)` | — |
| `MastStreamer` | MAST HTTP streaming | `stream(row, dir, read_timeout)`, `classify_failure(exc)` | 8 constants (see §Constants) |
| `S3FallbackDownloader` | `_s3_key_from_uri`, `_s3_download` | `key_from_uri(uri)`, `download(key, dest)` | `_S3_PUBLIC_BUCKET`, `_S3_TESS_KEY_PREFIX`, `_S3_KEPLER_KEY_PREFIX` |
| `FitsValidator` | `_is_valid_fits`, `_is_fits_corruption` | `is_valid(path)`, `is_corruption(exc)` | — |
| `DownloadCache` | `_try_serve_from_cache`, `_row_cache_path` | `serve(target, mission, dir)`, `path_for(row, dir)` | `_MAX_DOWNLOAD_SEGMENTS` |
| `SearchPrioritizer` | `_prioritize_search_results` | `rank(search_result, mission)` | — |
| `LightCurveDownloader` | `_download_tess_lightcurves` | `download(search_result, dir)` | composes above |
| `FusionBuilder` | `download_combined_fusion` | `fuse(safe_canonical)` | composes above |

Plus 3 seam modules:

- `_net.py` — `HttpClientPort`, `HttpResponse`, `RequestsHttpClient`,
  `FakeHttpClient`, and the fixture-recorder CLI.
- `_fs.py` — `FsPort`, `RealFs`, `FakeFs`.
- `_clock.py` — `ClockPort`, `RealClock`, `FakeClock`.

### `astraeus/core/archive/` (4 collaborators)

| Collaborator | Source it owns | Public methods |
|---|---|---|
| `MetadataNormalizer` | `normalize_target_name`, `sanitize_meta` | `normalize(raw)`, `sanitize(meta)` |
| `PsCompanion` | `_fetch_ps_orbital_period` | `fetch_period(safe_canonical)` |
| `ResponseParser` | raw TAP XML/JSON → dict | `parse(raw_response)` |
| `TapClient` | HTTP request, retry, response capture | `query(params)` |

### `astraeus/core/ingestion/` (3 collaborators)

| Collaborator | Source it owns | Public methods |
|---|---|---|
| `MissionResolver` | `_resolve_mission_target` | `resolve(meta, canonical, target_name)` |
| `BridgeBuilder` | `_bridge_to_time_series` | `build(meta, canonical, target_name, archive_error)` |
| `FetchCache` | `_cached_fetch_data` closure | `fetch(target_name, mission)` |

### `astraeus/data/loaders/` (4 modules)

`DataLoaderStrategy` ABC + `NASAArchiveLoader` + `CSVLoader` +
`JSONLoader`. Each in its own module. Strategy registration and
classmethod `DataFactory.load` stay in the facade.

### `astraeus/data/adapters/` (6 collaborators)

| Collaborator | Source it owns | Public methods |
|---|---|---|
| `CsvParser` | `_parse_csv` | `parse(path_or_buffer)` |
| `JsonParser` | `_parse_json` | `parse(path_or_buffer)` |
| `FitsParser` | `_parse_fits`, `_extract_fits_metadata` | `parse(path)`, `metadata(hdul)` |
| `ColumnScanner` | `_scan_columns`, `_resolve_columns` | `scan(columns)`, `resolve(df, mapping)` |
| `ArrayStandardizer` | `_standardize_arrays` | `standardize(time, flux, ferr)` |
| `AdapterCache` | `_preserve_in_streamlit` | `cached(callable, *args, **kwargs)` |

## Public facade preservation strategy

### The BWC promise

> After this refactor, every one of the 23 import sites compiles and runs
> unchanged. No constructor signature change. No method signature change.
> No return-shape change. No removal of any symbol any caller currently
> imports.

### Construction with optional DI

Every facade `__init__` accepts optional kwargs of the form
`collaborator_name: Protocol | None`. Defaults wire real collaborators —
production callers see no change.

```python
class LightkurveClient:
    def __init__(
        self,
        *,
        target_resolver: TargetResolverPort | None = None,
        cache_manager: CacheManagerPort | None = None,
        # ... 11 total
    ):
        self._targets = target_resolver or TargetResolver()
        # ...
```

`LightkurveClient()` (zero args) produces identical behavior to today.
Tests inject fakes via kwargs.

### Re-export of every internal symbol

Every module-level constant, helper, and class currently importable from
one of the 5 in-scope files remains importable after the refactor via
top-of-file re-exports:

```python
# astraeus/core/lightkurve_client.py
from astraeus.core.clients.mast_streamer import (
    _MAST_DOWNLOAD_URL, _TESS_READ_TIMEOUT, _KEPLER_READ_TIMEOUT,
    _CONNECT_TIMEOUT, _STREAM_CHUNK_BYTES, _STREAM_MAX_ATTEMPTS,
    _STREAM_BACKOFF_BASE,
)
from astraeus.core.clients.lightcurve_downloader import (
    _TESS_LC_DOWNLOAD_TIMEOUT, _TESS_LC_MAX_RETRIES, _TESS_LC_RETRY_BACKOFF,
)
# ... etc
```

### Identity preservation rule

Re-exports are re-bindings of the **same object**:
`astraeus.core.lightkurve_client._TESS_READ_TIMEOUT is astraeus.core.clients.mast_streamer._TESS_READ_TIMEOUT`
must be `True`. This is what makes monkeypatching of facade constants
still effective.

### The `NASAExoplanetArchive` classmethod pattern

Preserved via module-level singleton:

```python
# astraeus/core/nasa_archive.py
class NASAArchiveController:
    def __init__(self):
        self._normalizer = MetadataNormalizer()
        self._ps = PsCompanion()
        self._parser = ResponseParser()
        self._tap = TapClient()
    def fetch_metadata(self, canonical_name): ...

_default_controller = NASAArchiveController()

class NASAExoplanetArchive:
    @classmethod
    def fetch_metadata(cls, canonical_name):
        return _default_controller.fetch_metadata(canonical_name)
    @classmethod
    def normalize_target_name(cls, raw):
        return _default_controller._normalizer.normalize(raw)
    # ... etc
```

### The `_cached_fetch_data` module-level shim

`astraeus/core/ingestion.py:217` defines a module-level function with a
closure (`_inner_fetch`) implementing lru_cache semantics. Preserved:

```python
# astraeus/core/ingestion.py
class IngestionController:
    def __init__(self):
        self._resolver = MissionResolver()
        self._bridge = BridgeBuilder()
        self._cache = FetchCache()
    def _fetch_data_impl(self, target_name, mission):
        return self._cache.fetch(target_name, mission)

_default_controller = IngestionController()

def _cached_fetch_data(target_name, mission="Kepler"):
    return _default_controller._cache.fetch(target_name, mission)
```

### What we explicitly do NOT preserve

- **Internal call ordering** within a method — observable behavior
  only.
- **Internal variable names / private helper signatures**.
- **Exception types raised internally** — only the error-code string in
  the return tuple is contract.
- **Module-level underscore aliases that no caller imports** — these
  can be dropped unless the import-test gauntlet (§Verification) catches
  them.

## Reliability patch preservation

### The 17 constants and their owners

| # | Constant | Value | Owner |
|---|---|---|---|
| 1 | `_LIGHTKURVE_CACHE_DIR` | `~/.lightkurve/cache` | `CacheManager` |
| 2 | `_ASTRAEUS_LIGHTKURVE_CACHE_DIR` | env-overridable | `CacheManager` |
| 3 | `_MAX_DOWNLOAD_SEGMENTS` | `3` | `DownloadCache` |
| 4 | `_MAST_DOWNLOAD_URL` | `https://mast.stsci.edu/api/v0/Download/file` | `MastStreamer` |
| 5 | `_TESS_READ_TIMEOUT` | `600.0` | `MastStreamer` (FIX 2.3) |
| 6 | `_KEPLER_READ_TIMEOUT` | `180.0` | `MastStreamer` |
| 7 | `_CONNECT_TIMEOUT` | `10.0` | `MastStreamer` |
| 8 | `_STREAM_CHUNK_BYTES` | `1 << 20` | `MastStreamer` |
| 9 | `_STREAM_MAX_ATTEMPTS` | `3` | `MastStreamer` |
| 10 | `_STREAM_BACKOFF_BASE` | `2.0` | `MastStreamer` |
| 11 | `_S3_PUBLIC_BUCKET` | `stpubdata` | `S3FallbackDownloader` |
| 12 | `_S3_TESS_KEY_PREFIX` | `tess/public` | `S3FallbackDownloader` |
| 13 | `_S3_KEPLER_KEY_PREFIX` | `kepler/public` | `S3FallbackDownloader` |
| 14 | `_TESS_LC_DOWNLOAD_TIMEOUT` | `300.0` | `LightCurveDownloader` (orphan — see note) |
| 15 | `_TESS_LC_MAX_RETRIES` | `3` | `LightCurveDownloader` (orphan — see note) |
| 16 | `_TESS_LC_RETRY_BACKOFF` | `4.0` | `LightCurveDownloader` (orphan — see note) |
| 17 | `_TARGET_TIC_TABLE` | 10-entry dict | `TargetResolver` |

**Note on constants 14–16:** A grep of `lightkurve_client.py` confirms
`_TESS_LC_DOWNLOAD_TIMEOUT`, `_TESS_LC_MAX_RETRIES`, and
`_TESS_LC_RETRY_BACKOFF` are *declared at module level but never
referenced* in any function body — they appear to be leftovers from an
earlier refactor that replaced per-row streaming with `download_all()`.
They remain on the public module surface, so per the BWC promise they
must still be importable from `astraeus.core.lightkurve_client`. The
spec assigns ownership to `LightCurveDownloader` because the surrounding
comments ("SPOC LCs are ~1–2 MB each; 300s is generous for
download_all()") describe the SPOC download path. If the user prefers,
they can be moved to a dedicated `astraeus/core/clients/_legacy_constants.py`
module — the only contract is that they remain importable from the
facade.

### Config dataclass + facade-sourced defaults

Each collaborator that owns tunables reads from a frozen config
dataclass. Default construction uses facade-sourced values so
monkeypatching facade constants still works:

```python
# astraeus/core/clients/mast_streamer.py
@dataclass(frozen=True)
class MastStreamerConfig:
    mast_download_url: str = _MAST_DOWNLOAD_URL
    tess_read_timeout: float = _TESS_READ_TIMEOUT
    # ... 8 fields: _MAST_DOWNLOAD_URL, _TESS_READ_TIMEOUT,
    # _KEPLER_READ_TIMEOUT, _CONNECT_TIMEOUT, _STREAM_CHUNK_BYTES,
    # _STREAM_MAX_ATTEMPTS, _STREAM_BACKOFF_BASE, plus the default
    # read_timeout used by stream()

class MastStreamer:
    def __init__(self, config: MastStreamerConfig | None = None, ...):
        self._cfg = config or MastStreamerConfig()

# astraeus/core/lightkurve_client.py
class LightkurveClient:
    def __init__(self, *, mast_streamer=None, ...):
        if mast_streamer is None:
            cfg = MastStreamerConfig(
                tess_read_timeout=_TESS_READ_TIMEOUT,  # facade module global
                # ... all 8 MastStreamer fields read from facade module
            )
            self._mast = MastStreamer(config=cfg)
```

### Behavioral patches (not constants)

Each preserves a `### RELIABILITY:` comment header at the lines where
the logic lives:

- **np.float64 precision invariant** (file docstring §1–11) →
  `PrecisionGuard` + every array-constructing site.
- **TESS FFI streaming** (FIX 2.3, lines 31–33) → `MastStreamer.stream`.
- **MAST cache-staging trick** (lines 31–33) → `MastStreamer.stream`.
- **AWS S3 anonymous fallback** (lines 42–45) →
  `S3FallbackDownloader.download`.
- **TESS SPOC LC retry envelope** (lines 47–52) → `LightCurveDownloader`
  (orphan constants — see §5 note on constants 14–16).
- **Curated well-known target table** (lines 54–70) → `TargetResolver`.
- **Kepler row-by-row fallback limit** (line 29) → `DownloadCache`.

## Characterization & offline mocking strategy

### The principle

**We do not write new tests yet.** Section 3 is exclusively about
capturing current behavior and locking it in *before* any code moves.

### Network Intercept Layer (NIL)

`astraeus/core/clients/_net.py`:

```python
class HttpClientPort(Protocol):
    def get(self, url: str, *, timeout: float, stream: bool = False) -> HttpResponse: ...
    def head(self, url: str, *, timeout: float) -> HttpResponse: ...

@dataclass
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    iter_chunks: Callable[[int], Iterator[bytes]] | None
```

`RequestsHttpClient` wraps `requests.get` / `requests.head`.
`FakeHttpClient` (in `tests/_fixtures/fakes.py`) records calls and
returns scripted responses loaded from on-disk fixtures.

NIL plugs in at:

| Collaborator | Was | After NIL |
|---|---|---|
| `MastStreamer` | `requests.get` + `lightkurve` row download | `HttpClient.get` + `LightkurveRowPort` |
| `S3FallbackDownloader` | `requests.get` | `HttpClient.get` |
| `TapClient` | `requests.get` on TAP endpoint | `HttpClient.get` |
| `PsCompanion` | `requests.get` on PS API | `HttpClient.get` |

`LightkurveRowPort` is intentionally **narrow** — only
`row.download()`, `row.products`, `search_result.__iter__`. The full
`LightCurve` API is not emulated (ISP compliance).

### Filesystem & clock intercepts

```python
class FsPort(Protocol):
    def makedirs(self, path: str, exist_ok: bool) -> None: ...
    def exists(self, path: str) -> bool: ...
    def remove(self, path: str) -> None: ...
    def open(self, path: str, mode: str) -> BinaryIO: ...

class ClockPort(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
```

### Fixture recorder CLI

A one-shot CLI: `python -m astraeus.core.clients._net record --target
TRAPPIST-1 --mission TESS`. Runs against live MAST, captures responses
to disk under `tests/_fixtures/http_responses/`. Lightweight
domain-specific vcrpy.

JSON manifest format per fixture:

```json
{
  "url_pattern": "^https://mast\\.stsci\\.edu/api/v0/Download/file\\.\\.\\.",
  "method": "GET",
  "status": 200,
  "headers": {"Content-Type": "application/fits"},
  "body_b64": "...",
  "chunk_iter": null
}
```

Initial fixture batch:

- `mast_tess_stream_200.json`
- `mast_tess_stream_timeout.json`
- `mast_kepler_cache_hit.json`
- `s3_tess_anon_200.json`
- `s3_tess_anon_404.json`
- `nasa_tap_koi_70.json`
- `nasa_tap_trappist1.json`
- `ps_companion_wasp12.json`
- `fits_corrupt_truncated.fits` (binary)
- `fits_valid_minimal.fits` (binary)

### Characterization test plan

| Test file | Locks down |
|---|---|
| `tests/characterize/test_lightkurve_client_contract.py` | All branches of `download_pipeline` and `download_combined_fusion`: success, transient failure, corruption, missing cache. |
| `tests/characterize/test_nasa_archive_contract.py` | `normalize_target_name`, `sanitize_meta`, `fetch_metadata` for ~30 canonical names. |
| `tests/characterize/test_ingestion_contract.py` | `_fetch_data_impl` and `_cached_fetch_data` for success/cache-hit/cache-miss/archive-error. |
| `tests/characterize/test_data_loader_contract.py` | `DataFactory.load("nasa"/"csv"/"json", ...)` and module-level helpers. |
| `tests/characterize/test_data_adapter_contract.py` | `DataAdapter(bytes, name).parse()` for all three formats. |
| `tests/characterize/test_reliability_invariants.py` | All 17 constants preserved; np.float64 invariant; FIX 2.3 (≥600s). |
| `tests/characterize/test_facade_imports.py` | Every name currently imported from a refactored facade still resolves. |

Characterization tests:

- Use only fakes (`FakeHttpClient`, `FakeFs`, `FakeClock`,
  `FakeLightkurveRow`).
- Assert return shapes **and** error-code strings.
- Run in <2 s total.

### What stays network-only (explicitly excluded)

- `tests/test_nasa_archive_network.py` — keeps running against real
  NASA.
- `tests/test_debug_metadata_network.py` — same.
- `tests/test_global_matrix_stress_test.py`,
  `tests/test_pipeline_stress_test.py` — stress/integration; refactor
  must not break them, but we add no new characterization.

## Migration order & rollout

### Phase 0 — Land the seams (no production behavior change)

| Step | What |
|---|---|
| 0.1 | `astraeus/core/clients/_net.py` — `HttpClientPort`, `HttpResponse`, `RequestsHttpClient`, `FakeHttpClient` |
| 0.2 | `astraeus/core/clients/_fs.py`, `_clock.py` |
| 0.3 | `astraeus/core/clients/lightkurve_row.py` |
| 0.4 | Fixture-recorder CLI |
| 0.5 | Initial fixture batch (TRAPPIST-1, Kepler-11, WASP-12 b, plus failure variants) |

### Phase 1 — Lock down current behavior

| Step | What |
|---|---|
| 1.1 | `test_lightkurve_client_contract.py` |
| 1.2 | `test_nasa_archive_contract.py` |
| 1.3 | `test_ingestion_contract.py` |
| 1.4 | `test_data_loader_contract.py`, `test_data_adapter_contract.py` |
| 1.5 | `test_reliability_invariants.py` |
| 1.6 | `test_facade_imports.py` |

**Phase 1 exit criteria:** characterization suite green against
**unchanged** production code.

### Phase 2 — Extract leaf collaborators (lightkurve)

| Step | Collaborator |
|---|---|
| 2.1 | `PrecisionGuard` |
| 2.2 | `TargetResolver` + `_TARGET_TIC_TABLE` |
| 2.3 | `FitsValidator` |
| 2.4 | `CacheManager` |
| 2.5 | `TimeoutRunner` |
| 2.6 | `MastStreamer` |
| 2.7 | `S3FallbackDownloader` |
| 2.8 | `DownloadCache` |
| 2.9 | `SearchPrioritizer` |

### Phase 3 — Extract lightkurve orchestrators

| Step | What |
|---|---|
| 3.1 | `LightCurveDownloader` |
| 3.2 | `FusionBuilder` |
| 3.3 | `LightkurveClient` becomes a true facade (~80 lines) |

### Phase 4 — Other 4 in-scope files

Apply the same Phase 2/3 pattern to:

- `astraeus/core/nasa_archive.py` → `astraeus/core/archive/`
- `astraeus/core/ingestion.py` → `astraeus/core/ingestion/`
- `astraeus/data/loader.py` → `astraeus/data/loaders/`
- `astraeus/data/adapter.py` → `astraeus/data/adapters/`

### Phase 5 — Documentation & graph refresh

- Update `docs/ARCHITECTURE.md` with new package layout.
- Run `codegenome analyze` to refresh the architecture graph.
- Update `docs/superpowers/specs/` index.

### Per-step checklist

Every commit in Phase 2/3/4 must satisfy:

- [ ] New collaborator module(s) created with Protocol + class +
  module-level constants.
- [ ] Method body moved verbatim, including `### RELIABILITY:` comments.
- [ ] Config dataclass defines tunables with facade-sourced defaults.
- [ ] Facade method updated to delegate.
- [ ] Facade re-exports moved constants and helpers under original names.
- [ ] Characterization suite green (`pytest tests/characterize/ -x`).
- [ ] Existing in-scope tests green.
- [ ] `git diff --stat` shows net reduction in source-file line count.
- [ ] No file outside the in-scope 5 has been modified.

### Rollback strategy

Each Phase 2/3/4 step is one commit. If characterization goes red:

1. `git revert <sha>` — single commit, no other work lost.
2. Investigate which collaborator broke.
3. Fix in follow-up commit (re-apply revert + corrected version).

### Effort estimate

| Phase | Effort | Commits |
|---|---|---|
| Phase 0 (seams) | 0.5 day | ~5 |
| Phase 1 (characterize) | 1.0 day | ~6 |
| Phase 2 (lightkurve leaves) | 1.5 days | ~9 |
| Phase 3 (lightkurve orchestrators) | 0.5 day | ~3 |
| Phase 4 (other 4 files) | 2.5 days | ~22 |
| Phase 5 (docs) | 0.5 day | ~3 |
| **Total** | **~6.5 days** | **~48** |

## SOLID/SRP principle mapping

| Principle | How it's satisfied |
|---|---|
| **S**ingle Responsibility | Each collaborator owns one concern (e.g. `MastStreamer` owns MAST HTTP; `S3FallbackDownloader` owns S3; they don't bleed into each other). |
| **O**pen/Closed | New data sources (e.g. a future Gaia archive client) added by writing a new collaborator + Protocol, never by editing the facade. |
| **L**iskov Substitution | Every collaborator implements a Protocol. Any conforming impl can be swapped in (e.g. `FakeMastStreamer` in tests). |
| **I**nterface Segregation | Protocols are narrow. `LightkurveRowPort` covers only `row.download()`, `row.products`, `search_result.__iter__` — not the full `LightCurve` API. |
| **D**ependency Inversion | Facades depend on collaborator Protocols, not concrete classes. `LightkurveClient` depends on `MastStreamerPort`, not `MastStreamer`. Construction with kwargs makes injection trivial. |

## Risk register

| Risk | Mitigation |
|---|---|
| Accidentally delete a symbol a caller imports | `test_facade_imports.py` exhaustively checks every import site. |
| Change a constant value during extraction | `test_reliability_invariants.py` pins all 17 constants. |
| Drop `### RELIABILITY:` comments | Per-step checklist makes comment preservation explicit. |
| Introduce float32 somewhere | `PrecisionGuard` is the single owner; invariant test catches regressions. |
| Monkeypatching facade globals stops working | Config dataclass + facade-sourced defaults preserve identity. |
| Test currently patches `astraeus.core.lightkurve_client._X` and override is invisible | Same as above — facade reads its own module globals at construction. |
| `_cached_fetch_data` lru_cache semantics drift | `FetchCache` uses `functools.lru_cache` internally; behavior test covers it. |
| Future engineer "improves" curated target table | `_TARGET_TIC_TABLE` is a class attribute with the original 10 entries; adding entries is intentional but visible in PR review. |

## Acceptance criteria

- ✅ All 7 characterization test files green; run in <2 s.
- ✅ `pytest tests/characterize/ -x` — 100+ tests pass.
- ✅ `pytest tests/test_loader.py tests/test_adapter.py tests/test_nasa_archive_network.py tests/test_debug_metadata_network.py -x` — all pass.
- ✅ `astraeus/core/lightkurve_client.py` is <120 lines (excluding docstring + re-exports).
- ✅ Every public method on the 5 facade classes is ≤10 lines.
- ✅ Every collaborator has 1–3 public methods.
- ✅ All 17 constants re-exported at facade under original names.
- ✅ Every `### RELIABILITY:` comment header preserved at the collaborator that owns its logic.
- ✅ `python -m astraeus.core.clients._net record --target TRAPPIST-1 --mission TESS` produces a valid fixture.
- ✅ No file outside the in-scope 5 is modified by the refactor (verified by `git diff --name-only`).
- ✅ All 23 import sites compile and run unchanged (smoke import test).
- ✅ `codegenome analyze` shows reduced god-node scores for `lightkurve_client.py` (35 → <10), `nasa_archive.py`, `ingestion.py`, `loader.py`, `adapter.py`.

## Future specs (out of scope here)

- Subsystem 2: Analysis layer (`bls_search`, `detection`, `vetting`,
  `fitting`, `error_analysis`, `geometric_validation`, `ttv_*`,
  `reporting`, `detrending`).
- Subsystem 3: Simulation layer (`completeness`, `synthetic`).
- Subsystem 4: Workflows & Orchestrator (`pipeline`,
  `orchestrator`).
- Subsystem 5: Dashboard & Streamlit UI (`dashboard/services/*`,
  `dashboard/ui/*`, `dashboard/figures.py`, `app.py`,
  `ui/pages/*`).
- Subsystem 6: Diagnostics & QA harness
  (`tools/diagnostics/ultimate_stress_test.py`,
  `scripts/qa_runner*.py`, `tests/qa_*.py`).