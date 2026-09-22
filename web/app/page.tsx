"use client";

/**
 * Landing: one page, one job — send a researcher to the workbench with
 * an honest picture of what the instrument does. Real numbers (measured
 * in CI), a real curve (cached Kepler-90), zero synthesized science.
 */
import Link from "next/link";
import { ArrowRight, Flask, FolderOpen, MagnifyingGlass, ShieldCheck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import DemoCurve from "../components/DemoCurve";
import Reveal from "../components/Reveal";
import Starfield from "../components/Starfield";
import { API_URL } from "../lib/api";

const NUMBERS: Array<[string, string]> = [
  ["609", "tests green on the closeout gate"],
  ["6 / 6", "TLS thread-count pairs bit-identical"],
  ["3.2136 d", "Kepler-4d recovered at archive period"],
  ["0", "planet probabilities invented, ever"],
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

const ROUTES = [
  { href: "/investigate", title: "Investigate", body: "Run the blind search on real data.", icon: MagnifyingGlass },
  { href: "/analyses", title: "Analyses", body: "Durable jobs with provenance and download.", icon: FolderOpen },
  { href: "/simulate", title: "Simulate", body: "Seeded sandbox, labelled synthetic.", icon: Flask },
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

  return (
    <main className="landing">
      <div className="hero-wrap">
        <Starfield />
        <div className="hero-split">
          <div className="hero-load">
            <p className="eyebrow">Exoplanet transit analysis</p>
            <h1>Find planets in starlight, and prove every step.</h1>
            <p className="subtitle">Blind search, vetting, timing, retrieval — every result carries its provenance.</p>
            <div className="hero-ctas">
              <Link href="/investigate" className="cta-primary">
                Open the workbench <ArrowRight size={15} weight="bold" aria-hidden />
              </Link>
              <span className="mono muted">
                <span className={`status-dot ${alive === null ? "running" : alive ? "completed" : "failed"}`} />
                {health}
              </span>
            </div>
          </div>
          <div className="panel hero-chart hero-load" style={{ marginBottom: 0 }}>
            <DemoCurve />
          </div>
        </div>
      </div>

      <Reveal>
        <dl className="numbers-strip" aria-label="measured results">
          {NUMBERS.map(([value, label]) => (
            <div key={label}>
              <dt>{value}</dt>
              <dd>{label}</dd>
            </div>
          ))}
        </dl>
      </Reveal>

      <Reveal>
        <section className="panel">
          <h2>How a light curve becomes evidence</h2>
          <ol className="stage-rail">
            {STAGES.map((s) => (
              <li key={s.name}>
                <span className="stage-name">{s.name}</span>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
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
