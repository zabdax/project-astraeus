---
name: spectrahunt-ui
description: Design system and component architecture of the SpectraHunt web app (spectrahunt-web). Use when editing any route, component, style, or interaction in F:\NSAC-2026\spectrahunt\spectrahunt-web — codifies design tokens, component APIs, layout patterns, honesty rules, accessibility gates, and project footguns.
license: MIT
compatibility: Next.js 16.3.5 static export, React 19.2, TypeScript, Tailwind v4 (tokens in globals.css only), zustand 5. No component library, no animation library, no WebGL.
metadata:
  version: "1.0"
  skill-author: SpectraHunt team
---

# SpectraHunt UI

The app is a public blink comparator for NASA SPHEREx data. Every pixel must trace to
IRSA data or a cache of it. The UI already scores high on honesty, accessibility, and
offline behavior — elevation work must **add craft without breaking those contracts**.

## Non-negotiables (violating these fails the repo's own checks)

- **Honesty UI**: `png:null` renders metadata + "cutout pending"; unmeasured sky renders
  dark; unknown says "not yet surveyed". Never fabricate pixels, numbers, or status.
- **Cache-first layer contract**: localStorage → IndexedDB → network → honest fallback.
  Never block paint on an upstream fetch.
- **Static export**: no server code may `await searchParams`; read query state in effects
  or `useSearchParams` under `<Suspense>`.
- **Accessibility floor**: `role`/`aria-label` on canvases and custom controls, keyboard
  parity (Space/←/→/Ctrl+K/Esc), visible `:focus-visible`, `prefers-reduced-motion`
  variants for every animation, ≥44px touch targets.
- **Gates**: `npx eslint src` (0 errors), `tsc --noEmit`, `npm run build` (static export,
  bundle budget < 10 MB, currently ~3.3 MB). No new runtime deps without discussion.

## Stack facts

- Next.js **16.3.5** App Router, static export to `out/`. **Read
  `node_modules/next/dist/docs/` before assuming any Next API** (see AGENTS.md — this is
  not the Next.js from training data).
- React 19.2, TypeScript strict, zustand 5 (UI-only store: `compareMode`, `epochIdx`,
  `band`, `showMarkers`, `tutorialDone`). Routing state lives in URLs (`blinkURL()`).
- Styling: **one file**, `src/app/globals.css` (~700 lines). Tailwind v4 is imported but
  design tokens are CSS custom properties; component classes are hand-written BEM-ish
  (`.island`, `.glass`, `.ws-sec`, `.seg-btn`, `.epoch-chip`, `.film`, `.rtab`...).
- Icons: single SVG sprite (`components/Icon.tsx`) with `<use href="#i-*">` — add new
  icons as `<symbol>`s there, not new deps (lucide-react is installed but the sprite is
  the convention).

## Design tokens (globals.css `:root`)

| Token | Value | Use |
|---|---|---|
| `--space` / `--space-2` | `#05060c` / `#0a0c16` | page bg / raised bg |
| `--glass` / `--glass-strong` | `rgba(11,13,24,.72)` / `.93` | floating panels |
| `--raised` | `#151929` | inputs, chips |
| `--line` / `--line-strong` | `rgba(255,255,255,.09)` / `.2` | borders |
| `--ink` / `--ink-2` / `--ink-3` | `#eef0f8` / `#aab0c8` / `#8a90ab` | text ramp |
| `--focus` | `#a5acff` | focus ring |
| `--b1`…`--b6` | `#7c83fd #5aa9e6 #4fc9a8 #e8c34a #f08a4b #e85d4a` | 6 SPHEREx bands — **the brand spectrum** |
| `--spectrum` | linear-gradient b1→b6 | brand accent (logo ring, search focus) |
| `--known` `#5fcf9a`, `--unknown` `#f0bb52` | candidate semantics |
| `--font-display` | Bricolage Grotesque (variable opsz/wdth/wght) | hero + headings |
| `--font-ui` | Geist | body/UI |
| `--font-mono` | Geist Mono (`.mono`; tabular-nums on body) | coordinates, readouts |
| `--nav-h` 60px, `--nav-total` | nav height + safe-area |

Coverage levels `LEVEL_COLORS`: `null, #141a38, #1c2554, #27357a, #3848a8, #5a6ce0`
(deeper blue = more epochs). Stage/empty bg is always `#04050a`.


## Layout patterns

1. **Dynamic-island nav** (`.island`, `Header.tsx`): fixed floating pill, glass, brand +
   links + search icon + Surprise dice + mobile menu sheet. Ctrl/⌘K opens the command
   panel (`.cmd-veil`/`.cmd-panel`) from anywhere.
2. **Hero** (`HomePage.tsx` + `HeroSky.tsx`): full-viewport real 2MASS sky as a clickable
   mini-map, scrim gradient, centered search, featured-detection carousel (auto-cycles
   6s, pauses on hover/reduced-motion), stats band, 3-step how-it-works with inline SVG
   figures, first-visit `Tutorial` (localStorage `sh-tutorial`).
3. **Blink workspace** (`BlinkPage.tsx` + `BlinkComparator.tsx`): no page scroll on
   desktop. `.blink-grid` = tweak column (`.tweak-left.glass`: View/Display/Bands/Measure)
   + stage column (square `.stage-wrap`, transport row `.transport-row.glass`, filmstrip)
   + right rail with tabs (`.rtabs`: Overview/Epochs/Catalogs/Share). Canvas engine modes:
   blink/side/swipe/diff + false-color RGB; stretch (linear/log/sqrt/asinh) + colormaps
   (grayscale default, viridis/inferno/cividis) + invert, applied per-pixel in JS
   (`stylize()`). ⌘K palette (~25 commands), `?` guide, WebM/PNG export, in-browser ±5σ
   motion detection (`lib/motion.ts`) drives markers + Measure list.
4. **Sky page** (`/sky`): fullscreen, footer hidden. `StellariumView` observer POV
   (hips2fits SIN tiles, drag-look, pinch zoom, constellation figures, Gaia stars,
   Sun/Moon, cardinal ring, `.stel-hud` bottom bar) with `CoverageMap` all-sky toggle;
   `Inspector` rail (desktop) / bottom sheet (mobile).
5. **Candidates** (`/candidates`): `.cand-grid` of cards, badge semantics
   (`.badge.known`/`.unknown`, dot pulse), segment filter with counts, CSV/JSON export.
6. **About**: `.prose` column, band table with color swatches, tours, glossary, citation.

## Component APIs to respect

- `HeroSky`: `{grid, coverage, onInspect, markers?, onMarker?}` — canvas draws mirrored-X
  CAR bg + coverage tint + hover tooltip + click ripple; drag>5px ≠ click.
- `CoverageMap`: presentational; parent owns grid + selection. Same mirrored-X rule.
- `StellariumView`: `{focus, onInspect, initial, liveStars}` — gnomonic projection with
  **mirrored X** (`sx = cx − x·scale`); inverse must match exactly (hover = inverse of draw).
- `BlinkComparator`: `{frames, band, onBandChange, title, mode, onModeChange, epochIdx,
  onEpochChange, showMarkers, onToggleMarkers?, fovArcmin?, onSample?, center?, bandPngs?,
  onStats?}` — progressive preload (never cleared), DOM-direct histogram/diff stats (no
  react-state churn), non-passive wheel listener, reduced-motion disables autoplay.
- `SearchBox`: `{id, placeholder, compact?, onPick}` — combobox with grouped suggestions
  (coordinates/constellations/showcases/notable/catalogs), keyboard nav, shake-on-miss.
- `Inspector`: `{field, blinkId?, onClose, onOpenBlink}`.

## Data layer (`src/lib/`)

- `astro.ts` — coordinate parse/format (decimal, sexagesimal, colon), 88 constellations,
  102 LVF channels, `applyStretch`/`colormap`, `arcsecPerDay`, permalinks, `toCSV`, `mjdToDate`.
- `sky.ts` — `GRID_W=72 × GRID_H=36` coverage grid, `BANDS` (6, colors = tokens),
  `SKY_ALLSKY_URL`/`_PREVIEW_URL` (hips2fits CAR), `fmtRa/fmtDec`, `cellOf`, `drawBracket`.
- `showcases.ts` — 20 `SHOWCASE_IDS`, cache-first `getShowcase`/`getCoverage`, live mode
  (`NEXT_PUBLIC_DATA_MODE=live` + `NEXT_PUBLIC_API_URL`), `isLiveId`/`liveIdFor`/`parseLiveId`.
- `catalogs.ts` — SIMBAD-first/Sesame resolve, SkyBoT/MPC/Horizons/SIMBAD/IRSA link
  builders, `SURPRISE_FIELDS`, `TOURS`, `GLOSSARY`.
- `skycache.ts` — IndexedDB blob cache + 12-item objectURL LRU + `prefetch()` idle
  neighbor loading; localStorage JSON LRU (`lsGet/lsSet`).
- `motion.ts` — ≤96px downsample, MAD-noise ±5σ peaks, dipole pairing → movers/variables.
- `store.ts` — zustand UI store + `blinkURL()` permalink builder.

## Footguns (learned the hard way — encoded in comments)

- **RA increases LEFT** in the 2MASS CAR image: equirect draws mirror X
  (`ctx.translate(w,0); ctx.scale(-1,1)`); overlay math stays RA-right. SIN observer tiles
  use mirrored gnomonic; drag/inverse signs flipped to match.
- HiPS `Allsky.jpg` is a tile mosaic, **not** a map — never draw it as one.
- HeroSky click: suppress when pointer moved >5px (drag ≠ click).
- Histogram canvas reads `#blinkCanvas` with `willReadFrequently`; guard getImageData.
- Don't add `await searchParams` in any server component (breaks static export).
- `side-readout` is rendered twice in BlinkComparator (known duplication — fix carefully).

## Elevation surface map (where majestic work lands)

| Surface | File(s) | Opportunities |
|---|---|---|
| Hero | `HomePage.tsx`, `HeroSky.tsx`, hero CSS | scroll-driven reveal, kinetic display type (variable font axes), parallax depth, marker bloom, scrollytelling "how it works" |
| Nav/command | `Header.tsx` | springy island morph, palette polish, animated active pill |
| Blink stage | `BlinkComparator.tsx`, workspace CSS | mode transitions, crossfade on epoch change, filmstrip spring, transport micro-interactions, export progress states |
| Sky | `StellariumView.tsx`, `CoverageMap.tsx`, `SkyPage.tsx` | HUD glass upgrade, constellation label fade-by-zoom, marker hover bloom, smooth animated focus flights |
| Candidates | `CandidatesPage.tsx` | card stagger-in, hover lift + thumb crossfade blink, count-up stats |
| About | `AboutPage.tsx` | scroll reveals, band table as spectrum visualization |

Always pair with `majestic-web-ui` for technique and `canvas-sky-engine` for any canvas work.