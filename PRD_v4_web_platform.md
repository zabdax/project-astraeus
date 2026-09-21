# ASTRAEUS — PRD v4: Refined Web-Platform Plan (Research-Backed)

**Status:** Draft for review (planning only — no implementation started)
**Date:** 2026-09-16
**Supersedes:** `PRD_v3_web_platform.md`. v3's architecture is sound and survives; this version
corrects three factual errors, and adds the two sections v3 underweighted: **scientific accuracy
hardening** (the core of "more robust, more accurate") and **open-source credibility/positioning**.
**Research base:** 5 parallel live-web research streams, 2026-09-16. Every recommendation below is
cited; items that could not be verified are flagged, not asserted.

---

## 1. Executive summary — what changed since v3

v3's central finding holds: **this is a migration, not a rewrite.** The engine is framework-agnostic
Python (~13.5k LOC, 279 passing tests), the job model already exists (`submit_multi_planet_search` →
`get_job_status` → `cancel_job`), and there is zero REST/frontend code to untangle. What changed:

| v3 said | Research found | Correction |
|---|---|---|
| "Moving to Linux containers removes the `use_threads=1` constraint entirely" | CPython's `daemonic processes are not allowed to have children` assertion is in `Lib/multiprocessing/process.py:118-119` and fires on **every platform, including Linux**. Verified in the repo: `orchestrator.py:575-579` spawns `daemon=True`, and the code comment itself warns the fix requires changing *both* the daemon flag *and* the `use_threads=1` contract. | The unlock is **two coupled changes**, not an OS change: drop `daemon=True` + remove `use_threads=1`. Linux makes `daemon=False` safe (fork available, parent can reap); it does not remove the constraint by itself. Shipping the current orchestrator into a Linux container raises the *same* `AssertionError`. |
| "Next.js 14 (App Router)" | Current is **Next.js 16.3.3** (LTS). 16 shipped Turbopack-stable, Cache Components, React 19.2; 16.2 added a stable Adapter API for non-Vercel platforms. **Remix 3 forks Preact, not React** — it is no longer a React framework. | Upgrade the target to **Next.js 16**. Remove Remix from consideration entirely. |
| FastAPI + "SSE or WebSocket" (undecided) | **FastAPI 0.135+ has native SSE** — `fastapi.sse.EventSourceResponse`/`ServerSentEvent`, 15s keep-alive, `X-Accel-Buffering: no`, and `Last-Event-ID` resumption built in. | **SSE, not WebSocket.** And it must be served **directly from the FastAPI origin**, never proxied through Vercel (Hobby max duration is 300s — exactly our worst-case job; body limit 4.5 MB). |
| Postgres/SQLite and Qdrant deferred (correct) | Confirmed and sharpened: arrays must **never** live in the DB; FastAPI Users is in **maintenance mode**; Cloudflare Workers free tier is **10 ms CPU/request** and Python Workers doesn't support numpy. | Wire format = **Apache Arrow over HTTP** (~1.95 MiB vs ~4.8–6.2 MiB JSON for an 80k×3 light curve); auth = **own JWT + `ASTRAEUS_SINGLE_USER=1` mode**. |

**And two things v3 missed entirely, both of which serve your stated goal directly:**

- **A reproducibility landmine:** `batman`, `transitleastsquares`, and `wotan` are **not in `requirements.txt`** — they are lazy `try/except` imports with silent fallbacks. A container without them silently degrades to a median filter, a trapezoid model, and **no TLS cross-validation**, raising no error. Your science output can differ between desktop and container with no warning. *(§4.1 — highest urgency)*
- **The accuracy gaps the migration is the right moment to fix:** unseeded MCMC by default (`seed=None`) with no convergence gate; a detection floor calibrated on *signals* rather than *noise*; unweighted χ² in V-shape vetting plus an `snr>10` override that labels high-SNR grazing eclipsing binaries as "Likely Planet"; four different limb-darkening assumptions across pipeline stages. *(§4)*

---

## 2. Refined, validated tech stack

Everything below was verified live against primary sources on 2026-09-16.

### 2.1 Frontend & visualization

| Decision | Choice | Why (cited) |
|---|---|---|
| Framework | **Next.js 16 (App Router)** | `use client` boundary keeps Plotly/Three.js off marketing bundles; streaming SSR for dashboard shells; **stable Adapter API = no Vercel lock-in**; largest React contributor pool for an OSS project. https://nextjs.org/docs |
| — *reject* | ~~Remix 3~~, ~~SvelteKit~~, ~~Astro+Next split~~ | Remix 3 forks **Preact** — you'd forfeit the R3F/Plotly/RHF ecosystem you're betting on. SvelteKit: wrong talent/eco fit. Astro-for-marketing doubles maintainer surface. https://remix.run/blog/wake-up-remix |
| Rich figures | **Keep Plotly JSON** — upgrade `plotly.py 5.24.1 → 7.1.0` | Your `plotly.py 5.24.1` emits **plotly.js 2.x** JSON; plotly.py 7.1.0 bundles plotly.js 4.1.1. plotly.js 4's breaking changes (mapbox traces, MathJax v2) **don't touch `scatter`/`scattergl`**, so light-curve figures carry forward. **But the full bundle is 4.63 MB / 1.40 MB gzip** — shipping it naively *is* the plotting regression you must not make. Use a partial bundle (`react-plotly.js/factory` + `lib/index-basic`) and route-level lazy-load. https://github.com/plotly/plotly.js |
| Big time-series | **uPlot** for the flagship light curve | Canvas, 0 deps, **50.8 KB gzip vs Plotly's 1.40 MB**, 166,650 points in 25 ms. Two planned gaps: no built-in drag-pan (plugin needed), low-level imperative API. https://github.com/leeoniya/uPlot |
| — *spike* | **Apache ECharts 6** as single-library alt | Tree-shakeable to reasonable size; `dataZoom`/`brush`/linked charts built in. https://echarts.apache.org |
| 3D orbits | **react-three-fiber + three.js + drei** | React-native scene graph; a straight port of the HTML/JS orbit animation you already emit. Lazy-loaded on the 3D route only. https://r3f.docs.pmnd.rs |
| — *reject* | ~~Babylon.js~~, ~~deck.gl~~, ~~Plotly 3D~~ | Babylon: no first-class React. deck.gl: map-centric. Plotly 3D drags the full bundle onto the route. |
| Forms | **React Hook Form + Zod** (+Zustand for global state) | `useFieldArray` for add/remove planets; isolated re-renders so N planets × M sliders don't re-render each other; one Zod schema encodes physical bounds (0<e<1, i∈[0,180]) **and** can be generated from the API (§2.3). https://react-hook-form.com |
| Monorepo | **pnpm workspaces + Turborepo** | Python stays under `uv`/`pyproject.toml` wired as a Turbo task so JS and Python CI cache together. Nx is Python-community-plugin-only; skip. https://turborepo.dev |
| API contract | **hey-api/openapi-ts** | Generates TS types **+ typed SDK + Zod schemas** from FastAPI's `/openapi.json`. The generated Zod feeds RHF's `zodResolver` → **server Pydantic models and client validation share one source of truth.** This closes the loop v3 left open. https://github.com/hey-api/openapi-ts |

### 2.2 Backend, compute & data

| Decision | Choice | Why (cited) |
|---|---|---|
| API framework | **FastAPI** | Native SSE, OpenAPI, Pydantic v2. **Critical bridging rule:** `run_in_threadpool` = `anyio.to_thread.run_sync` is a *thread pool* — non-blocking but **GIL-bound, zero parallelism** for numpy. Endpoints stay `async def` (I/O only); engines **never** run in the request path. https://fastapi.tiangolo.com/async/ |
| Job queue v1 | **Custom: SQLite job table + asyncio supervisor + `subprocess.Popen(start_new_session=True)`** | Zero extra containers; **full kill semantics** (cancel = `os.killpg(SIGTERM)` → `SIGKILL` after grace); durable via DB replay; startup reclaims stale `RUNNING` rows. ~300–500 LOC. |
| Job queue v2 | **arq + Redis** (same worker contract) | arq doesn't fork (avoids OpenBLAS fork-safety hazards); jobs not removed until done; `Job.abort()` available. The arq task body is just "spawn the subprocess and stream stdout" — **a dispatcher change, not an engine change.** |
| — *reject* | ~~Celery~~, ~~TaskIQ~~, ~~Dramatiq~~, ~~Temporal/Prefect/Dagster~~, ~~FastAPI BackgroundTasks~~ | Celery: in-memory revokes, blunt `terminate`, **no Windows support**. TaskIQ: **no task abort** (their own comparison table). **Dramatiq is LGPL-3.0** (copyleft risk). Temporal/Prefect/Dagster: **cooperative cancellation cannot hard-kill a wedged numpy process** — the exact capability we need. BackgroundTasks: in-process, non-durable, dies with uvicorn. |
| — *reject* | ~~Docker-in-Docker per job~~ | Mounting `/var/run/docker.sock` = host root. If isolation is ever needed: rootless Docker + user namespaces, or a non-root worker with cgroup memory caps. |
| Array wire format | **Apache Arrow IPC over HTTP** | 80k float64 × 3: **~1.95 MiB vs ~4.8–6.2 MiB JSON** (~3× smaller, and JSON serialization CPU is what Dash explicitly complains about). Decoded in-browser by `apache-arrow` npm via `tableFromIPC(fetch(...))`. Bokeh already ships binary buffers, not JSON, for the same reason. |
| Array at rest | **Parquet in object store** (local volume v1 → S3/R2) + metadata in DB | DuckDB-WASM does byte-range queries over HTTP. **Arrays never go in the DB** — it holds `artifact_ref` + dtype/shape/n_cadence. |
| Database | **SQLite (WAL) v1 → PostgreSQL (asyncpg) prod** | Use `BEGIN IMMEDIATE` + `busy_timeout` + WAL. **Alembic `render_as_batch=True`** from day one so migrations are portable SQLite→Postgres. |
| Auth | **Own JWT on `OAuth2PasswordBearer` + `ASTRAEUS_SINGLE_USER=1`** | **FastAPI Users is in maintenance mode** ("no new features… a new toolkit will supersede it") — don't adopt. Model `users` + `job.owner_id` **from day one** even with one row. `SINGLE_USER` mode follows JupyterHub's `DummyAuthenticator` precedent for local-only binds. |
| LLM gateway | **Keep existing `LLMClient`, route everything through an OpenAI-compatible interface** | **Ollama is MIT-licensed** and exposes an OpenAI-compatible API — so local/air-gapped model support is nearly free and is a genuine differentiator for institutions with data-residency constraints. **Never ship provider keys in the demo image** (BYOK only). |

### 2.3 Deployment

| Decision | Choice | Why (cited) |
|---|---|---|
| Self-hosted | **`docker compose up`** — one multi-arch image (uv-built) + **Caddy** for zero-config HTTPS | Follow Appwrite/Supabase patterns: `${VAR:-default}` on every value, `healthcheck` + `depends_on(condition: service_healthy)`, named volumes, `profiles: [gpu][ollama]`. |
| — *reject* | ~~single static binary~~ | Measured: `kaleido==0.2.1` alone is **81.2 MB** (bundles a headless Chromium); numpy/scipy/matplotlib/pandas ≈ 87 MB more; C extensions are platform-specific and **PyInstaller is not a cross-compiler**. A "binary" would be ~500 MB, need 3 OS builds, and still need a browser. |
| Public demo | **Vercel Hobby (frontend only) + Fly.io or Hetzner VPS for API/worker** | **Truly-$0 compute does not exist for CPU-bound science.** Budget ~$3–6/mo as the project's one hard cost. |
| — *reject* | ~~Vercel serverless for jobs~~, ~~Cloudflare Workers compute~~, ~~Render free tier~~ | Vercel Hobby: **300s max duration AND hard cap**, **4.5 MB body**. CF Workers free: **10 ms CPU/request**; Python Workers doesn't support numpy. Render: free web services **spin down after 15 min idle**; **free Postgres expires 30 days after creation**. |
| Secrets | **`.env` dev → Docker secrets for compose → sops+age for the repo's own secrets** | Per-user LLM keys: **default to pass-through BYOK** (key lives in browser session, never persisted); server-side storage opt-in, envelope-encrypted, `GET /settings/keys` returns masked last-4 only. |
| Env/repro | **`uv` lockfile** (or `pixi` if conda-only bins are needed) | `uv.lock` + `--locked`; Astral's layered Docker recipe (cache-mount `uv sync --locked --no-install-project` before `COPY .`). |

### 2.4 Licensing & open-source machinery

| Decision | Choice | Why (cited) |
|---|---|---|
| License | **Apache 2.0 — decide now, not later** | Over MIT purely for the **explicit patent grant + retaliation clause**, which matters for a numerical-methods tool and smooths institutional legal review. **Time-boxed:** MIT→Apache-2.0 is one commit *today* while you're sole copyright holder; after contributors land it needs a DCO/CLA or individual consent. Use **DCO (`Signed-off-by`)**, not a CLA. |
| — *reject* | ~~AGPLv3~~ as SaaS protection, ~~SSPL/BSL~~ | **Verified: AGPL §13 triggers only on *modified* versions** — hosting *unmodified* Astraeus triggers nothing. So AGPL doesn't solve the stated worry while costing full copyleft. SSPL/BSL aren't OSI-approved → **disqualified from JOSS and NumFOCUS**. Solve "someone hosts my tool" with a managed demo + community, not a license. |
| Docs | **Docusaurus** | Versioned docs matter for a research API with breaking changes; it's what scientific OSS expects. Avoid Mintlify (closed-source host, off-message for an OSS project). |
| Releases/deps | **release-please** (Conventional Commits → release PR + changelog) + **Renovate** + **pre-commit** + matrix CI | Renovate's grouped/peers-aware updates handle pinned scientific deps better than Dependabot. |
| Telemetry | **Opt-in, off by default in self-hosted builds**, public telemetry doc | Plausible for site analytics (cleanest privacy story); PostHog only if you need feature flags for staging the copilot. |
| Credibility path | **ASCL entry → Zenodo DOI per release → JOSS submission** | AAS Data Editors review 90–100% of submissions for software citation and name ASCL the "1-stop shop"; JOSS mints a **Crossref DOI** and requires an **OSI-approved license** (which independently reinforces the Apache-2.0 call). **Without these, astronomers will not cite results produced in a browser.** |
| Funding | **GitHub Sponsors first** (0% fees on personal accounts) → Open Collective if you need a legal entity → NumFOCUS fiscal sponsorship as a 2–3 year goal | NumFOCUS fiscal sponsorship requires >1 contributor, distributed governance, roadmap, public CoC — treat those as the roadmap, not paperwork. |

---

## 3. The performance unlock (do this in Phase 0)

This is the single largest performance win available, and it is currently **locked by a contract test**.

**Today:** `orchestrator.py:575-579` spawns the search worker with `daemon=True`. CPython's
`Lib/multiprocessing/process.py:118-119` asserts daemonic processes cannot have children, which
forces `detection.py` to run TLS with `use_threads=1` — costing **~80 s per call** on a 45,853-cadence
curve. The repo comment states the constraint explicitly and warns that changing it requires
updating `tests/characterize/test_tls_call_path_contract.py`.

**The fix is two coupled changes, done together:**
1. Spawn the worker **non-daemon** (`daemon=False` + `start_new_session=True` so cancel can still
   kill the whole process group).
2. Remove the `use_threads=1` contract in `detection.py`, letting TLS instantiate
   `multiprocessing.Pool(processes=cpu_count())`.

**Expected speedup:** TLS's period grid is embarrassingly parallel (`imap_unordered` over pure
`search_period` calls — verified in the TLS source). Estimate **~80 s → ~10–14 s on 8 cores
(6–8×)**, bounded by pool startup and the serial pre/post phases. *That is an engineering estimate
from the code structure, not a benchmark* — the repo already holds the profiling artifact
(`logs/j2c_tls_profiling_result.json`); re-run it with `use_threads=cpu_count()` on a Linux box to
put a real number in the plan before committing to it.

**Why it lowers the bar for the queue:** the queue's job stops being "tolerate 80 s serial TLS inside
a daemon" and becomes "spawn a short-lived non-daemon process that forks its own pool, and kill that
whole tree on cancel" — exactly what the §2.2 supervisor gives you and what cooperative-cancellation
systems cannot do. **Do not** run the engine in-process inside a fork-based worker (RQ's horse,
Celery's prefork child) and then fork a Pool from *that* — nested pools interact badly with OpenBLAS
thread pools; a clean `Popen` of a dedicated worker script sidesteps it.

---

## 4. Scientific accuracy & robustness hardening

*This is the section that serves your "more robust, more accurate, highly good" requirement directly.
Every item below was verified against the code and against the literature.*

### 4.1 URGENT: silent scientific degradation (fix in Phase 0, before anything else)

**`batman`, `transitleastsquares`, and `wotan` are not in `requirements.txt`.** They are lazy
`try/except` imports with silent fallbacks:

| Module | Missing backend | Silent fallback | Consequence |
|---|---|---|---|
| `analysis/detrending.py:4` | `wotan` | median filter | Coarser detrending; median filters are the classic transit-depth killer when the window ≈ transit duration |
| `analysis/detection.py:62` | `transitleastsquares` | no TLS cross-validation | The J2c TLS gate — a headline vetting step — **silently doesn't run** |
| `core/orchestrator.py:32` | `batman` | trapezoid model | Signal subtraction uses a cruder model, which over/under-subtracts and can **manufacture phantom additional planets** |

**This is a live reproducibility bug right now, independent of the migration:** your desktop and a
Docker container can produce *different science* with no error raised. Fix: make all three **hard
dependencies** in `requirements.txt`/`uv.lock`, and make the pipeline **refuse to run** (not silently
degrade) if a scientific backend is missing. All three are MIT-licensed, so there is no licensing
obstacle. *(Note: TLS's PyPI metadata has an empty license-classifier list — worth an upstream PR.)*

### 4.2 "Where we could silently be wrong" — ranked

| # | Risk | Evidence | Mitigation |
|---|---|---|---|
| 1 | **Unconverged MCMC posteriors that look fine.** `seed` defaults to `None` (legacy unseeded `np.random.randn`); fixed 20% burn-in; walkers clustered in a `1e-4` ball around the optimizer's best fit — if the optimizer is in a local minimum, *all* walkers are. No τ, no R-hat, no ESS, no acceptance gate. | emcee's own tutorial: chains should exceed ~50τ; *"you probably shouldn't trust any estimate of τ unless you have more than F×τ samples for some F ≥ 50"*; you must **not** compute Gelman-Rubin across chains in one ensemble because *"the chains are not independent."* Modern standard = rank-normalized R-hat + bulk/tail ESS (Vehtari et al. show GR-1992 *"has serious flaws"*). | Make `seed` non-optional with a documented default; report `get_autocorr_time()`; require steps ≥ 50τ; run **2–4 independent ensembles** and compute rank-R-hat via **ArviZ**; gate on mean acceptance fraction ∈ [0.2, 0.5]; replace fixed 20% burn-in with burn-until-τ-stable. |
| 2 | **Detection floor calibrated on signals, not noise.** `DETECTION_CONFIDENCE_FLOOR = 7.0` is documented in-code as *"NOT a FAP — empirically fit to the synthetic sweep."** | TLS derives its SDE→FAP mapping from **>10,000 noise-only runs** (0.9→5.7 … 0.9999→9.1); community convention is **SDE > 9**; and with real (red) noise *"the FAP estimates are too optimistic."* | Run a noise-only calibration suite; **publish your floor's true FAP**. This converts a magic number into a defensible statistical threshold — and it is a publishable result in itself. |
| 3 | **Unweighted χ² in V-shape vetting + `snr>10` override.** | Δχ² is only on a significance scale if χ² is **weighted** (`Σ((f−m)/σ)²`); with equal free parameters the comparison is really an AIC comparison. Worse, **grazing eclipsing binaries are high-SNR**, so the `snr>10` override actively converts the *worst* false-positive class into "Likely Planet." | Weight the χ²; remove or tightly gate the SNR override; add **odd/even transit-depth comparison** and **ephemeris matching** as standard Kepler-pipeline gates. |
| 4 | **Four different limb-darkening assumptions across stages.** | `sensitivity_engine` = uniform disk; detection = TLS LD-aware; fitting = quadratic (u1,u2, bounds [0,1]); subtraction = fixed `u=[0.1,0.3]`. Same system, four models. | One LD source of truth threaded through all stages. Switch fitting to **Kipping q1,q2** sampling (efficient, uninformative) with **Claret power-2** priors — fixing LDCs to theory *"can give rise to important systematic errors which directly impact… the planetary radius."* |
| 5 | **Depth↔limb-darkening covariance.** | The Transit-Depth Precision Problem: amplification factor A should be ~√3 but reaches **≳10** *"notably due to correlations between D and the limb-darkening coefficients."* | Report the **D–u1–u2 posterior covariance**, not just marginals. |
| 6 | **Detrending window vs transit duration.** Fixed 0.5–2.0 d windows can absorb transits (esp. USP / long-duration). | TLS scales trial durations from **stellar-density priors**; wotan benchmarked all common methods against hundreds of real planets. | Scale the window from stellar density/duration priors; **never use `savgol`/`median_filter` fallbacks in production** (fixed by §4.1 making wotan a hard dep). |
| 7 | **Fixed-geometry subtraction model.** `inc=90`, `ecc=0`, `a ≈ P/(π·duration)` small-angle approximation. | Over/under-subtraction manufactures residual signal read as extra planets. | Fit LD per subtraction rather than fixing; mask in-transit before re-detrending; keep the existing harmonic/duplicate guard. |

### 4.3 Inference engine: keep emcee, add gates (do NOT rewrite)

**Keep emcee.** Rewriting the forward model in PyTensor to move to `exoplanet`/PyMC for gradient-based
NUTS would mean rewriting your custom analytic geometry + `quad_vec` + batman — none of it
differentiable there — **during a platform migration**. That is exactly how accuracy regresses. The
literature confirms emcee remains the long-tail standard; `exoplanet`'s own docs show the project split
into celerite2/pymc-ext (2018–2021). **Value is accuracy; rewrite mid-migration is the risk.**

Defer `dynesty` (dynamic nested sampling) unless you later need Bayesian **model comparison**
(planet vs EB vs grazing) for vetting — it gives evidence, emcee doesn't. **Do not** go BLS-only:
grazing/V-shaped transits are TLS's documented weak case, so the BLS+TLS cross-validation you already
have is the right design.

### 4.4 Reproducibility contract (the honest version)

Define reproducibility as **"same seed + same pinned env (incl. BLAS) ⇒ statistically identical
posterior," not bit-identical.** PyTorch's reproducibility docs state plainly that *"completely
reproducible results are not guaranteed across… different platforms"* and *"floating-point addition
is not associative"*; the same applies to any BLAS-backed numpy/scipy math. Do **not** promise or test
bit-comparability Windows↔Linux.

Concretely: pin the full env in the container (incl. batman/wotan/TLS per §4.1); set
`PYTHONHASHSEED=0` and fixed thread counts (`threadpoolctl` or `OMP_NUM_THREADS`); seed **every** RNG;
and write a `provenance.json` next to every result containing **git SHA, lockfile hash, exact
scientific-package versions, all seeds, BLAS thread counts, `cpu_count()`, and CPU model**. Offer a
strict `--bit-exact` mode that pins single-threaded BLAS for archival runs. Zenodo-DOI each release.

### 4.5 Validation strategy — the "accuracy proof" you can publish

This is what converts "trust me" into a citable claim, and it uses assets you already have
(`run_injection_recovery`, `nasa_archive.py`).

- **Reference catalogs:** Kepler DR25 KOI catalog (canonical ground truth for long-baseline recovery),
  TESS Objects of Interest, Sullivan et al. FP simulations (calibrates expected false-positive rate
  against theory), Coughlin et al. ephemeris-matching methods.
- **Canonical targets spanning your branches:** Kepler-10 b / Kepler-78 b (deep USP filter),
  Kepler-9 b/c/d (multi-planet TTV), TRAPPIST-1 (resonant chain, N-body), Kepler-186 f / 452 b
  (long-period completeness limit), K2-32 / Kepler-160 (the systems TLS's own survey papers used).
- **Metrics to report (publishable):** detection-efficiency curve vs injected (period, depth); false-positive
  rate vs Sullivan predictions; median + 95th-percentile |ΔP/P|; depth accuracy + D–LDC covariance;
  **CDPP** as the community-standard noise yardstick; and your own noise-only SDE→FAP calibration.
- **CI gates:** a seeded sub-minute **injection-recovery suite** (recovery rate ≥ threshold,
  median |ΔP/P| ≤ tolerance); **hypothesis** property tests on deterministic geometry/unit code (never
  on stochastic MCMC output — use seeded golden-master + statistical-tolerance assertions there);
  **asv** continuous benchmarking (what numpy/scipy/astropy actually use) — this matters once you
  containerize, because the §3 unlock changes the performance profile.

---

## 5. Competitive positioning & the credibility paradox

### 5.1 The gap is real and verified

**Every exoplanet transit tool is a local Python library.** Live GitHub data (2026-09-16): lightkurve
(532★, MIT, library-only), TLS (63★, MIT, library+CLI), astropy BLS (library), batman (105★, GPL,
forward-model only), juliet (68★, library), exoplanet (239★, PyMC library), EXOFASTv2 (50★, **IDL**,
~2 yr stale), EXOTIC (123★, **the only one with a GUI**, and it ships Colab notebooks precisely to
dodge the install problem). **None is a hosted end-to-end pipeline.**

**The institutions that host the data deliberately stop at discovery:** Exo.MAST (search only),
ExoFOP (users upload *already-derived* parameters), **ExoCTK** (lists light-curve fitting as a
capability of the *GitHub package only* — no web tool), NASA Exoplanet Archive (ADQL catalog only).

**The user pain is verified, not assumed** — read from the actual issue trackers: TLS #103 *"Dependency
on batman / numpy makes it impossible to install TLS"*, #104 M1 Macs spawning *"a seemingly infinite
loop of processes"*; lightkurve #1565–#1590 (CBV naming mismatches forcing manual file renames,
`detect_filetype()` crashing on ~40M TARS light curves, `flatten(niters=0)` leaking an
`UnboundLocalError` that *"gives no indication of which argument caused it"*).

> **Positioning:** *the only hosted, zero-install, end-to-end path from "a Kepler/TESS target ID" to
> vetted candidates and MCMC posteriors — with a transparent pipeline and an AI interpreter — for the
> audience that finds `exoplanet`+PyMC, IDL-based EXOFASTv2, or a broken TLS install inaccessible.*

### 5.2 The three differentiators, evidence-ranked

1. **Zero-install end-to-end pipeline in the browser.** Nothing verified does this. Highest value,
   hardest to copy (requires stitching TLS-class detection + vetting + emcee into a durable service).
2. **Integrated false-positive vetting as part of discovery.** Detection tools stop at a periodogram;
   `astropy` BLS offers `compute_stats` but leaves interpretation to the user; ExoFOP's V-shape labels
   are *human-entered*, not computed. Your V-shape / secondary-eclipse / USP filters, automated and
   explained, have no verified equivalent anywhere.
3. **AI copilot for interpretation.** `exoplanet`/PyMC's learning curve is exactly the barrier your
   audience hits; the direction of travel is clear (astroEDU already added an "AstroEDU Agent").

### 5.3 The moat is NOT data — and the credibility paradox

**Verified: there is no data or licensing moat.** MAST requires no API key and documents no rate limits
(only a ~500k-row query cap); STScI content is *"freely used as in the public domain"* with an
acknowledgment requirement; the Exoplanet Archive is now **TAP/ADQL, keyless** (`pscomppars` is
TAP-only — the legacy composite table is retired); lightkurve is MIT. **Anyone can build this.**
Differentiation must come from UX + integrated vetting + **trust and reproducibility**.

**The paradox you must plan for:** your "fully transparent pipeline" claim cuts both ways.
Astronomers will not cite results from an uncited web app. **ASCL + Zenodo DOI + JOSS are not
optional polish — they are the difference between a research tool and a teaching toy.** And the AI
copilot actively fights the transparency claim unless every inference it makes is auditable. AAS
Data Editors review **90–100% of submissions** for software citation; the `\software{}` LaTeX tag is
expected. Budget the credibility work as a first-class deliverable, not an afterthought.

### 5.4 Threats

- **MAST/STScI could build it** — low probability today (ExoCTK explicitly keeps fitting out of the
  browser) but they already have the portal, the data, the limb-darkening calculator, and institutional trust.
- **LLMs collapse the differentiator** — "ChatGPT + Colab + lightkurve" is a real substitute for the
  zero-install value prop. Defend on **vetting rigor and reproducibility provenance**, not "AI explains results."
- **Compute economics** — MCMC at scale on free tiers is unsustainable. This is a cost moat *against* you.
- **Lightkurve could add a GUI** — firmly library-only today, but it already steers users to hosted notebooks.

---

## 6. Updated roadmap

Phases 0–4 from v3 survive; the accuracy and credibility work is now folded in at the right points.
**Constraint unchanged: Streamlit stays live and green until Phase 3 exit — it is the side-by-side
QA reference, and nothing in `astraeus/core` or `astraeus/analysis` is rewritten, only wrapped.**

| Phase | Duration | Deliverables | Exit gate |
|---|---|---|---|
| **0 — Decouple & harden** | ~2 wks | §4.1 make batman/wotan/TLS hard deps + refuse-to-run; §3 daemon/`use_threads` unlock (with `test_tls_call_path_contract.py` **updated**, not deleted); remove the 2 Streamlit leaks; consolidate the duplicated MCMC/N-body paths; re-route live pages through the service layer; write Pydantic contracts; surface swallowed TLS errors as job error states; **switch license MIT→Apache 2.0** (time-boxed, sole author) | Full suite green; engine imports with Streamlit uninstalled; container science == desktop science (no silent degradation) |
| **1 — API + durable jobs** | ~2–3 wks | FastAPI per §2; SQLite supervisor (v1) with process-group cancel; **native SSE from the API origin**; Arrow wire format + Parquet object store; own JWT + `SINGLE_USER` mode; `provenance.json` per result | Every endpoint contract-tested; a job survives server restart; cancel actually kills the process tree |
| **2 — Frontend, feature parity** | ~4–6 wks | Next.js 16 shell → Discover → Detective → Simulation → Lab/History/Settings; uPlot light curve + Plotly partial bundles + R3F orbits; **openapi-ts → Zod → RHF** loop; e2e tests | All 6 routes at parity, dark theme matched, side-by-side QA vs Streamlit |
| **3 — Accuracy + real copilot** | ~3 wks | §4.2 fixes: emcee convergence gates + seeded by default; weighted χ² + SNR-override removal; Kipping q1,q2 + single LD source of truth; odd/even + ephemeris-matching vetting gates; wire `LLMClient` into the chat with SSE streaming (BYOK, OpenAI-compatible incl. Ollama); settings persistence | Noise-only FAP calibration published; copilot returns real streamed output grounded in the active session |
| **4 — Validation, deploy, deprecate** | ~3 wks | Injection-recovery CI gate + asv benchmarks; validation runs against Kepler DR25 / TOI reference targets; Docker Compose + Caddy self-host; Fly.io/Hetzner demo; **ASCL entry + Zenodo DOI; JOSS checklist started**; freeze Streamlit behind `--legacy` | Detection-efficiency curve + FP-rate comparison published; `docker compose up` works cold; DOI minted |

**Sequencing rationale:** §4.1 (silent degradation) is Phase 0 because *the migration makes it worse
the moment you containerize* — containerizing a silently-degrading pipeline bakes the wrong science
into a reproducible artifact. The accuracy work sits in Phase 3, after parity, because it changes
numerical behavior and must be validated against the Streamlit baseline, not smuggled in alongside a
UI rewrite.

---

## 7. Risk register (deltas on v3)

| Risk | Change | Mitigation |
|---|---|---|
| **The daemon unlock breaks the locked contract test** | NEW — `test_tls_call_path_contract.py` pins `use_threads=1` *by design* | Update the test and the `detection.py` comment as part of the same change; re-profile with the repo's own `logs/j2c_tls_profiling_result.json` methodology before committing to a speedup figure |
| **Silent backend degradation in containers** | NEW, highest severity | §4.1 hard deps + refuse-to-run; a CI matrix that asserts batman/wotan/TLS are importable |
| **MCMC results change when seeded + gated** | NEW — expected and *desired*, but it changes numbers users may have saved | Announce as a versioned scientific change in the release notes; keep the old path available behind a flag for one release |
| **Vercel traps silently break the demo** | Sharpened | SSE and big payloads **always** served from the FastAPI origin; frontend is static-only on Vercel |
| **plotly.js bundle = the regression you must not make** | NEW | Partial bundle + `next/dynamic` lazy-load; uPlot for the flagship light curve |
| **Credibility paradox blocks adoption** | NEW | Phase 4 treats ASCL/Zenodo/JOSS as deliverables, not nice-to-haves |
| *(retained)* session_state hidden couplings; `detective.py` is a rewrite in disguise; scope creep from `prd_v2.md`'s aspirational features | unchanged | v3 mitigations stand: contracts-first, port Detective last, defer Qdrant/LangGraph with a re-entry trigger |

---

## 8. Decisions needed before Phase 0

**Carried from v3** (my recommendations unchanged): SQLite-first; in-process supervisor v1 then arq;
single-user auth with a `users` table from day one; monorepo with `frontend/`+`backend/`.

**New decisions from this research:**

1. **License: switch to Apache 2.0 now?** Recommended — the patent grant matters and the switch is
   free only while you're the sole copyright holder. Confirm and I'll do it as a single commit with a
   NOTICE file.
2. **Performance unlock in Phase 0?** It changes numerical behavior (multi-threaded TLS) and requires
   updating a locked contract test. High value, but it's a scientific-behavior change — your call on
   timing.
3. **Make the accuracy fixes (§4.2) a dedicated Phase 3, or interleave them into Phase 0?** Dedicated
   is safer (validate against the Streamlit baseline); interleaved is faster if you're confident.
4. **JOSS as an explicit Phase 4 deliverable?** It needs 6 months of public history and
   feature-completeness — worth confirming as a goal now because it constrains licensing and testing.
5. **Copilot provider default.** `config.json` currently defaults to `google`/`gemini-1.5-pro-latest`.
   Research suggests standardizing on an **OpenAI-compatible interface with Ollama as the zero-cost
   air-gapped option** — keep Google as default, or go provider-neutral?

---

## 9. What could not be verified (flagged, not asserted)

- **The ~6–8× TLS speedup** is an estimate from TLS's verified `imap_unordered` period-grid structure,
  **not a benchmark.** Re-profile before quoting it.
- **numpy→Arrow zero-copy** is documented only in the Arrow→numpy direction; confirm with a
  buffer-address comparison or wrap with `pa.Array.from_buffers`.
- **Multithreaded-BLAS reduction determinism** — no authoritative NumPy statement found; treat the
  §4.4 caveat as engineering folklore, not cited fact.
- **Zenodo concept-DOI vs per-version mechanics** — the `help.zenodo.org` sub-pages 404'd.
- **OpenAI's Terms-of-Use** (competing-model clause) returned HTTP 403; the Anthropic AUP *was*
  verified (no general competing-product ban). Don't assert OpenAI specifics until read.
- **Hetzner current list prices** — JS-rendered page, API requires a token.
- **AAS reproducibility policy pages** return Cloudflare 403; the AAS *software-citation* policy was
  verified, the reproducibility report was not.
- **Community-forum pain evidence** (Stack Exchange, Reddit) — search engines were unusable; the
  pain-point analysis rests on **GitHub issue trackers only**.
- **NAAP/UNL astronomy simulations** (astro.unl.edu) — SSL failure; an existing transit-simulator
  applet in the education space could not be ruled out.

*Tooling note (per `AGENTS.md`):* CodeGenome MCP was unavailable again for this pass (no native tools;
HTTP probe of `http://127.0.0.1:7331/mcp` → `000`). Direct repo reads were used throughout, including
by the research agents. **Before Phase 0, run `codegenome analyze` or `codegenome mcp-start --transport
http`** so the migration can be tracked against a current graph. Also note: `.agents/skills/astraeus-architecture/SKILL.md`
describes the layout as `src/astraeus/`, but the actual package root is `astraeus/` — the skill is
stale and worth updating before future agents rely on its paths.
