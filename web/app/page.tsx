"use client";

/**
 * Landing: the intro page. A 3D transit scene opens the story, three
 * persona doors route each visitor to their workflow, and measured
 * numbers + the pipeline + provenance close it. Real curve data only
 * appears downstream; the hero scene is labelled illustration.
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  ArrowRight,
  FileText,
  FolderOpen,
  GraduationCap,
  MagnifyingGlass,
  Planet,
  ShieldCheck,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import CountUp from "../components/CountUp";
import DemoCurve from "../components/DemoCurve";
import Reveal from "../components/Reveal";
import { API_URL } from "../lib/api";

const TransitHero = dynamic(() => import("../components/TransitHero"), {
  ssr: false,
  loading: () => <div className="skeleton" style={{ height: "clamp(420px, 62vh, 600px)" }} aria-label="loading 3D scene" />,
});

const NUMBERS: Array<{ display: string; value: number | null; decimals?: number; suffix?: string; label: string }> = [
  { display: "609", value: 609, label: "tests green on the closeout gate" },
  { display: "6 / 6", value: null, label: "TLS thread-count pairs bit-identical" },
  { display: "3.2136 d", value: 3.2136, decimals: 4, suffix: " d", label: "Kepler-4d recovered at archive period" },
  { display: "0", value: 0, label: "planet probabilities invented, ever" },
];

const STAGES = [
  {
    name: "Detect",
    body: "Box Least Squares sweeps the light curve; Transit Least Squares must confirm the peak or the candidate dies here.",
  },
  {
    name: "Vet",
    body: "U-shape against V-shape, secondary-eclipse hunt, ultra-short-period tripwires. Grazing binaries fail loudly.",
  },
  {
    name: "Time",
    body: "Transit timing variations extracted per epoch — dynamics hiding in the residuals, not smoothed away.",
  },
  {
    name: "Retrieve",
    body: "MCMC posteriors with convergence gates. An unconverged chain raises instead of returning silent numbers.",
  },
];

const DOORS = [
  {
    href: "/simulate",
    title: "Learn the physics",
    body: "Tune period, depth, inclination on a seeded sandbox and watch the orbit, the light curve and the residuals answer. Built for students meeting transits for the first time.",
    meta: "no account · labelled synthetic",
    icon: GraduationCap,
  },
  {
    href: "/investigate",
    title: "Discover planets",
    body: "Point the blind search at a real Kepler, K2 or TESS target — or drop in your own curve — and get vetted candidates with evidence, not scores.",
    meta: "connect · real data",
    icon: Planet,
  },
  {
    href: "/analyses",
    title: "Publish the proof",
    body: "Every job persists with provenance, warnings and downloads. Reproduce any run from its own record and export the manuscript.",
    meta: "durable · reproducible",
    icon: FileText,
  },
];

const ROUTES = [
  { href: "/investigate", title: "Investigate", body: "Run the blind search on real data.", icon: MagnifyingGlass },
  { href: "/analyses", title: "Analyses", body: "Durable jobs with provenance and download.", icon: FolderOpen },
];

export default function Home() {
  const [health, setHealth] = useState<string>("checking…");
  const [alive, setAlive] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((b) => {
        setAlive(true);
        setHealth(`v${b.version} · single-user: ${String(b.single_user)}`);
      })
      .catch(() => {
        setAlive(false);
        setHealth("unreachable — start the API first");
      });
  }, []);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    function onScroll() {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        document.documentElement.style.setProperty("--scroll", String(max > 0 ? window.scrollY / max : 0));
      });
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <main className="landing">
      <div className="scroll-progress" aria-hidden />
      <div className="hero3d-wrap">
        <div className="aurora" aria-hidden>
          <span />
          <span />
        </div>
        <TransitHero />
        <div className="hero3d-health glass mono muted">
          <span className={`status-dot ${alive === null ? "running" : alive ? "completed" : "failed"}`} />
          Pipeline status: {health}
        </div>
        <div className="hero3d-copy">
          <div className="hero-load">
            <p className="eyebrow">Exoplanet transit analysis</p>
            <h1>Find planets in starlight, and prove every step.</h1>
            <p className="subtitle">Blind search, vetting, timing, retrieval — every result carries its provenance.</p>
            <div className="hero-ctas">
              <Link href="/investigate" className="cta-primary">
                Open the workbench <ArrowRight size={15} weight="bold" aria-hidden />
              </Link>
              <Link href="/simulate" className="cta-primary" style={{ background: "transparent", color: "var(--accent)", border: "1px solid var(--accent-dim)" }}>
                Try the sandbox
              </Link>
            </div>
            <div className="scroll-cue" aria-hidden>
              scroll — the instrument tour
            </div>
          </div>
        </div>
      </div>

      <Reveal>
        <dl className="numbers-strip" aria-label="measured results">
          {NUMBERS.map((n) => (
            <div key={n.label}>
              <CountUp value={n.value} decimals={n.decimals ?? 0} suffix={n.suffix ?? ""} display={n.display} />
              <dd>{n.label}</dd>
            </div>
          ))}
        </dl>
      </Reveal>

      <Reveal variant="scale">
        <section aria-label="choose your path">
          <div className="doors">
            {DOORS.map((d) => (
              <Link key={d.href} href={d.href} className="door glass">
                <d.icon size={26} weight="duotone" aria-hidden />
                <strong>{d.title}</strong>
                <p>{d.body}</p>
                <span className="mono">{d.meta} →</span>
              </Link>
            ))}
          </div>
        </section>
      </Reveal>

      <Reveal>
        <section className="panel">
          <div className="prov-grid">
            <div>
              <h2>A real curve, really observed</h2>
              <DemoCurve />
            </div>
            <div>
              <h2>How a light curve becomes evidence</h2>
              <ol className="stage-rail">
                {STAGES.map((s) => (
                  <li key={s.name}>
                    <span className="stage-name">{s.name}</span>
                    <p>{s.body}</p>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>
      </Reveal>

      <Reveal>
        <section className="panel">
          <h2>Provenance, not promises</h2>
          <div className="prov-grid">
            <pre className="dump">
{`"tls": {"attempted": true, "n_ran_fail": 1},
"capability": {"tls": true, "wotan": true},
"dataset_id": "sha256 over arrays, not metadata"`}
            </pre>
            <div>
              <p>
                A completed job with zero candidates is a <em>measured negative</em> — the TLS gate ran and
                rejected the peak. The record states exactly that.
              </p>
              <p className="muted">
                <ShieldCheck size={14} weight="duotone" aria-hidden /> Fail-closed at every gate: missing backends,
                unconverged chains, and infrastructure faults surface as reasons, never as silent passes.
              </p>
            </div>
          </div>
        </section>
      </Reveal>

      <Reveal>
        <section className="honesty-band">
          <h2>What this instrument will not show you</h2>
          <p>
            No planet probability — the engine computes no such quantity. No mock copilot — unconfigured AI says
            so instead of inventing. No hidden inference — that field stays null until Phase 4 wiring lands.
          </p>
        </section>
      </Reveal>

      <Reveal>
        <section className="panel">
          <h2>Start working</h2>
          <div className="route-rows">
            {ROUTES.map((r) => (
              <Link key={r.href} href={r.href} className="route-row">
                <r.icon size={18} weight="duotone" aria-hidden />
                <span>
                  <strong>{r.title}</strong>
                  <span className="muted"> — {r.body}</span>
                </span>
                <ArrowRight size={15} aria-hidden />
              </Link>
            ))}
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            Settings lives in the top bar — connection, keys, and exactly what is stored where.
          </p>
        </section>
      </Reveal>
    </main>
  );
}
