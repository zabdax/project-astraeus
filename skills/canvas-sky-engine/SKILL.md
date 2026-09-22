---
name: canvas-sky-engine
description: Canvas 2D engineering patterns for SpectraHunt's sky surfaces (HeroSky, CoverageMap, StellariumView, BlinkComparator stage, WaitGame). Use when editing any canvas rendering, pointer interaction, projection math, or image-loading pipeline — covers DPR handling, RAF discipline, mirrored projections, hit-test parity, caching, and reduced-motion loops.
license: MIT
compatibility: Browser Canvas 2D only (no WebGL by design). React 19 with refs + effects, no render-loop state.
metadata:
  version: "1.0"
  skill-author: SpectraHunt team
---

# Canvas Sky Engine

SpectraHunt renders real sky imagery on Canvas 2D with overlay math. These are the
patterns the existing code follows — any new canvas work must match them.

## The four surfaces

| Component | Surface | Projection | Orientation rule |
|---|---|---|---|
| `HeroSky` | full-viewport hero | equirect CAR bg (cover-fit) | **mirror X on draw** (`translate(w,0); scale(-1,1)`), overlay math RA-right |
| `CoverageMap` | all-sky map | same CAR bg + 72×36 tile grid | same mirrored-X rule |
| `StellariumView` | observer POV | gnomonic (hips2fits SIN tiles) | **mirrored**: `sx = cx − x·scale`; inverse + drag signs flipped |
| `BlinkComparator` | square stage | cover-fit cutouts | pan/zoom in screen space; RA/Dec probe uses mirrored offset signs |

Never assume orientation. When touching projection code, re-verify against a real frame
(SYSTEM_DESIGN.md §7). HiPS `Allsky.jpg` is a tile mosaic — never draw it as a map.

## Render-loop discipline (all surfaces follow this)

- All mutable render state lives in `useRef` objects, never React state — one
  `state.current` bag updated by an always-current-effect; a `cb.current` ref holds
  latest callbacks. React state only for things that change the DOM tree.
- **Kick-based RAF**: `const kick = () => { if (!raf) raf = requestAnimationFrame(tick) }`
  — draw only when dirty (pointer move, resize, image arrival, visibilitychange).
  Continuous loops (ripples, autoplay, WaitGame) self-cancel when idle/hidden/reduced.
- DPR: `canvas.width = w * min(devicePixelRatio, 2)`; `ctx.setTransform(dpr,0,0,dpr,0,0)`;
  re-run on `ResizeObserver` of the host element.
- Text on dark imagery: `strokeText` with `rgba(5,6,12,.85)` halo then `fillText`
  (see CoverageMap `label()`).
- DOM-direct updates (histogram, diff stats) write to refs/canvas — no react-state churn
  in pointermove handlers.

## Imagery pipeline

- Two-stage load: preview URL first (720×360), full res after; shimmer/loading state
  covers the cold first paint (never blank confusion).
- All loads go through `lib/skycache.ts`: in-memory objectURL LRU (12) → IndexedDB blob
  store (`spectrahunt-sky/tiles`, 4MB cap) → network. `prefetch()` warms neighbor views
  in `requestIdleCallback`.
- `crossOrigin='anonymous'` on every `Image` (canvas pixel sampling requires clean CORS);
  guard every `getImageData` in try/catch (tainted canvas → degrade gracefully).
- `willReadFrequently: true` on contexts that get sampled per-frame.

## Interaction parity (the golden rule)

**Hover/click math must be the exact inverse of draw math.** If draw mirrors X, the
hit-test mirrors X. When you change a projection, change both in the same commit.

- Pointer events on the canvas; drag threshold (~5px) separates click from pan.
- Touch: `touch-action:none` on draggable surfaces; pinch = two-pointer distance ratio.
- Wheel listeners must be registered non-passive when calling `preventDefault`
  (React 19 attaches passive by default on root — use a ref + `addEventListener`).
- Keyboard parity for everything the pointer can do; `role="img"` + descriptive
  `aria-label` (include current center/FOV) on every canvas.

## Reduced motion

Every loop checks `window.matchMedia('(prefers-reduced-motion: reduce)')`:
static first frame renders, animation loops never start (WaitGame draws a static
starfield; hero skips ripples; autoplay never starts). Also pause on
`document.hidden` / `visibilitychange`.

## Adding effects without breaking the frame budget

- Composite effects in the same RAF pass as the scene draw — never a second listener.
- Prefer additive `globalCompositeOperation = 'lighter'` glows (cheap) over shadowBlur
  (expensive per-frame).
- Precompute per-frame invariants (cell rects, label positions) outside the loop.
- Keep per-frame allocations at zero — reuse typed arrays (`lib/motion.ts` pattern).
- If a marker/glow bloom is added, animate a single `t0`-seeded parameter and derive
  radius/alpha from it (see HeroSky ripple pattern).
