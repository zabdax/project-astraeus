---
name: majestic-web-ui
description: Award-winning UI elevation techniques for SpectraHunt — motion language, spring physics, glassmorphism, kinetic typography, micro-interactions, scrollytelling, and the performance/accessibility guardrails that separate majestic from gimmicky. Use whenever upgrading any visual surface or interaction in spectrahunt-web.
license: MIT
compatibility: CSS-first (scroll-driven animations, linear() springs, backdrop-filter); no runtime animation deps preferred — the project enforces a <10MB bundle and no new deps without discussion.
metadata:
  version: "1.0"
  skill-author: SpectraHunt team
  research-date: "2026-09-22"
---

# Majestic Web UI

Distilled 2026 craft standards (Awwwards/Webby winners, GSAP/MotionKit 2026 reports,
motion-UX research) adapted to SpectraHunt's constraints: static export, hand-written
CSS, canvas surfaces, zero heavy deps, strict a11y.

## Prime directives

1. **Motion is the brand layer.** In 2026, rhythm/weight of motion says more than
   microcopy. Treat motion as designed system behavior, not decoration.
2. **Restraint wins.** Fewer, more purposeful effects. What faded in 2026: autoplay
   entrance animations on everything, scroll-hijacking, decorative preloaders, heavy
   hero videos, anything that stutters.
3. **Performance is the trend.** Motion is judged by INP (200ms threshold). Every effect
   must run off the main thread where possible (CSS transform/opacity, canvas RAF).
4. **Reduced-motion parity is table stakes.** Every motion pattern ships with a reduced
   variant (crossfade or instant state change). SpectraHunt already does this — keep it.
5. **Motion for mood, copy for meaning.** Never let animation carry information alone.

## The motion token system (add to globals.css as `--motion-*`)

Formalize 4–5 tokens; they cover ~80% of the product surface:

| Token | Suggested value | Use |
|---|---|---|
| `--ease-spring` | `linear(0,.5 1.8%,1.01 3.6%,1.11 7%,1.13 11%,1.01 24%,1 36%)` | snappy settle (native CSS spring via `linear()`) |
| `--ease-out-expo` | `cubic-bezier(.16,1,.3,1)` | entrances, reveals |
| `--dur-tap` | `120ms` | presses, toggles |
| `--dur-ui` | `220ms` | panel popovers, chips |
| `--dur-page` | `450ms` | route/mode transitions, inspector slide |
| `--stagger` | `35–60ms` | list/card reveal cadence |

Rules: exits faster than entrances (~60–70% duration); nothing interactive > 500ms;
large distances use springs, small distances use ease-out.

## Techniques that read "majestic" (with implementation)

### Spring physics over bezier
CSS now supports `animation-timing-function: linear(...)` spring approximations — zero
JS. Use for the island nav morph, inspector sheet, palette open, card hover lift. JS
springs only when interruption mid-flight matters (canvas-driven values).

### Scroll-driven CSS animations (baseline 2026)
`animation-timeline: scroll()` / `view()` — no JS, compositor-friendly:
- Hero headline: scale/letter-spacing drift tied to scroll; scrim deepens.
- "How it works" steps: `view()`-triggered reveal + the 3 SVG figures draw-in
  (stroke-dashoffset path animation — cheap and elegant).
- Numbers band: count-up triggered by `view()`, once.
Wrap in `@media (prefers-reduced-motion: no-preference)`; provide
`@supports not (animation-timeline: view())` fallback = visible final state.

### Glassmorphism 2.0 (depth-aware, restrained)
The project has `.glass` — elevate it: keep blur(18px) saturate(1.3); add a 1px gradient
border (mask technique) and scroll-reactive brightness. Limit glass to floating chrome
(nav, panels, chips) — never behind body text. Check APCA contrast against the blurred
content beneath, not just the solid base color.

### Tactile micro-details (2026 skeuomorph revival, done right)
Layered `box-shadow` with inset press states on buttons (`:active` translateY(1px) +
inner shadow); ultra-subtle grain overlay (SVG `feTurbulence` noise, ~3% opacity,
`pointer-events:none`, fixed) to kill banding on dark gradients. Neumorphism failed on
contrast — borrow tactility, never sacrifice legibility.

### Kinetic / variable typography
Bricolage Grotesque is already variable (opsz 12–96, wdth 75–100, wght 400–800): animate
`font-variation-settings` on hero hover/scroll (weight breathe, width stretch).
Per-word/letter reveal with staggered translateY+opacity for the hero H1. Body text
stays static — kinetic type is for display sizes only.

### Cursor & hover micro-interactions
Magnetic hover on primary CTAs (translate toward cursor ≤6px, spring back); spectrum
ring sweep on search focus (extend `--spectrum` into a rotating conic-gradient border);
marker bloom on hero/sky canvases (hover → soft glow ring + label fade-in, drawn in the
canvas RAF loop).

### Scrollytelling & bento reveals
Home/About: pinned sections where the visual (real cutout pair) stays while text steps
through the story — use CSS `position: sticky`, never scroll-jacking. Bento-grid reveal
for the fields rail: cards fade+rise with `view()` stagger.

### 3D/WebGL: touch only
Canvas-2D by design (offline, bundle budget). Cheap depth instead: multi-layer parallax
starfield (2–3 canvas layers at different scroll/drag factors), CSS `perspective` tilt
on candidate cards (≤2deg), blurred duplicate behind glass for faux refraction.

## Space-site inspiration benchmarks (studied)

- **NASA Solar System Exploration** (Webby winner): entity-first content, living
  visualizations powered by real APIs — "the sky as it really is: moving, evolving."
  Lesson SpectraHunt already embodies: real data IS the visual identity.
- **Stellarium Web**: minimal chrome, HUD bottom bar, sky owns the viewport — matched by
  `/sky`; elevate the HUD with glass + springy popovers.
- **Awwwards space-site patterns**: near-black (not pure black) bg, one accent gradient,
  oversized display type with tight tracking (hero already does
  `clamp(2.7rem,7.2vw,5.4rem)` / `line-height:.98` — correct), hairline 1px rules, mono
  coordinate readouts used as texture.

## Anti-patterns (do not ship)

- No lerp smooth-scroll libraries, no scroll-jacking.
- No entrance animation below the fold without a `view()` trigger.
- No blur > 24px, no glass behind paragraphs.
- No animation that can't finish in 500ms on a mid-range Android.
- No new runtime deps (GSAP/Framer) without explicit discussion — CSS + canvas RAF cover
  the design space; if JS springs are truly needed, write a 20-line integrator.
- Never animate `width/height/top/left` — transform + opacity only (canvas excepted).

## Review checklist before merging any elevation PR

- [ ] Every animation has a `prefers-reduced-motion` variant.
- [ ] No layout-triggering properties animated; INP-safe (no long tasks > 50ms).
- [ ] Contrast checked against the actual blurred backdrop (APCA).
- [ ] Works at 360px and keyboard-only.
- [ ] `eslint`, `tsc --noEmit`, `npm run build` clean; bundle delta justified.
- [ ] Honesty rules intact — motion never implies data that isn't there.
