# SpectraHunt Agent Skills

Project-local skills for UI work on SpectraHunt. Format follows the
`scientific-agent-skills` convention: one folder per skill, a `SKILL.md`
with YAML frontmatter (`name`, `description`), optional `references/`.

| Skill | Use when |
|---|---|
| [`spectrahunt-ui`](./spectrahunt-ui/SKILL.md) | Any change to `spectrahunt-web`: routes, components, `globals.css`, canvases, state. Codifies the design system, component APIs, honesty rules, and footguns. |
| [`majestic-web-ui`](./majestic-web-ui/SKILL.md) | Elevating any surface to award-winning quality: motion language, glass, kinetic type, micro-interactions, performance/accessibility guardrails. Distilled 2026 best practices. |
| [`canvas-sky-engine`](./canvas-sky-engine/SKILL.md) | Touching any canvas surface (HeroSky, CoverageMap, StellariumView, BlinkComparator stage): DPR, RAF discipline, projections, caching, hit-test parity. |

## Vendored from the ecosystem (upstream sources, kept verbatim)

| Skill | Author | Use when |
|---|---|---|
| [`frontend-design`](./frontend-design/SKILL.md) | Anthropic | Choosing a bold, intentional aesthetic direction; avoiding "AI slop" design. |
| [`taste-skill`](./taste-skill/SKILL.md) | Leonxlnx | Brief-inference and anti-default discipline for landing/redesign work; forbidden-pattern list. |
| [`emil-design-eng`](./emil-design-eng/SKILL.md) | Emil Kowalski | Component-level polish: exact transitions, press states, transform origins, review checklists. |
| [`animate`](./animate/SKILL.md) | Emil Kowalski | Building any animation/transition from scratch — the decision order that makes motion feel right. |
| [`apple-design`](./apple-design/SKILL.md) | Emil Kowalski | Fluid physical motion, gesture-driven UI, materials/depth, interruptible transitions. |
| [`animation-vocabulary`](./animation-vocabulary/SKILL.md) | Emil Kowalski | Naming motion effects precisely ("pop in", "rubber-banding") for prompts and reviews. |
| [`build-awwwards-quality-sites`](./build-awwwards-quality-sites/SKILL.md) | Meng To | Art direction + acceptance bar for the orbital intro / hero as the site's strongest authored moment. |
| [`landing-page-design`](./landing-page-design/SKILL.md) | Elaya Design | One-page-one-job structure, hero copy, section sequence, visual system rules. |

Rules that outrank everything else (from `ARCHITECTURE.md` / `docs/FRONTEND.md`):

1. **Honesty UI** — never synthesize pixels or numbers; missing data renders as missing.
2. **Cache-first** — stale beats missing; missing renders honestly; never block UI on upstream.
3. **Lint is law** — `npx eslint src` 0 errors, `tsc --noEmit` clean, `npm run build` passes.
4. **Static export** — nothing server-side may `await searchParams`; client-only query state.
5. **Orientation is verified, never assumed** — 2MASS CAR: RA increases LEFT; mirror X on draw.
