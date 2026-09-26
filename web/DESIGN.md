# ASTRAEUS — DESIGN.md

AI-readable design system for the web frontend (`web/`). Generated from
`app/globals.css` — edit the CSS first, then update this file.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#070A12` | page |
| `--bg-raise` | `#0B101D` | inputs |
| `--panel` / `--panel-2` | `#0D1424` / `#141C31` | panels (vertical blend only) |
| `--line` / `--line-soft` | `#1E2A46` / `#16203A` | borders |
| `--text` / `--muted` / `--faint` | `#DDE5F3` / `#8F9BB3` / `#5D6A87` | text ramp |
| `--accent` | `#6CB0FF` | ONLY saturated UI hue |
| `--ok` / `--warn` / `--bad` | `#3ECF8E` / `#E5B567` / `#F26D6D` | verdict semantics only |
| `--radius-panel` / `--control` / `--badge` | `14px` / `8px` / `4px` | the only radii |
| `--font-display` / `--mono` | Space Grotesk / IBM Plex Mono | voice / every number |
| `--ease-spring` | `linear(...)` | chrome springs |
| `--ease-out-expo` | `cubic-bezier(.16,1,.3,1)` | reveals |
| `--dur-tap` / `--dur-ui` / `--dur-page` | `120ms` / `220ms` / `450ms` | timing scale |

## Rules (no AI slop)

- Dark-locked. No light theme, no purple-blue gradients, no glow-as-decoration.
- One accent hue. Data ramps (plasma/inferno) never leak into chrome.
- Mono for every number (tabular-nums). Sentence case. One eyebrow per region max.
- Motion answers action or marks one orchestrated load. Nothing interactive > 500ms.
- Transform + opacity only (canvas excepted). Every animation ships reduced-motion parity.
- Grain overlay 5% fixed kills banding; glass only on floating chrome.

## Components

- `.panel` — workbench card. `.workspace` — 340px rail + results (1col < 900px).
- `.badge.measured/.derived/.inferred/.ai` — epistemic class, never decoration.
- `.numbers-strip` — measured-number band, count-up on view.
- `.stage-rail` — vertical timeline, scroll-linked fill via `view()`.
- `.route-rows/.route-row` — divide-y navigation, not a card grid.
- `.orbit-console` — 3D orbit: toolbar (play + transit flag + hint) + canvas.
- `.run-meter` — SSE job progress (`--p` 0..1) + `.run-phase` mono readout.
- `.eventlog` — mono SSE tail. `details.provenance` — progressive disclosure.
- `.hero-wrap` + `.starfield` — 3-layer parallax canvas + drifting chart panel.
- `.scroll-progress` — 2px hairline, `--scroll` owned by JS.
- `.reveal` / `.reveal-scale` — IO-triggered entrances, once.

## Canvas discipline

Refs hold render state, never React state. Kick-based RAF, DPR ≤ 2,
`ResizeObserver`/resize re-fit, `visibilitychange` parks loops,
`touch-action:none` + non-passive wheel where `preventDefault` is needed.
Hover math is the exact inverse of draw math.
