"use client";

/**
 * P3-D Simulate route: a synthetic sandbox, honestly labelled.
 * Curves generated here are SYNTHETIC by construction (trapezoid +
 * seeded noise) and every downstream number inherits that label.
 * Submitting sends them through the real detection pipeline as an
 * inline dataset — injection-recovery on demand.
 */
import Link from "next/link";
import { useMemo, useState } from "react";
import LightCurve from "../../components/LightCurve";
import OrbitView from "../../components/OrbitView";
import { getJob, submitInlineDataset } from "../../lib/api";
import { binFolded, foldToPhase } from "../../lib/fold";
import { circularDurationDays, impactParameter, semiMajorAxisAu } from "../../lib/orbit";
import { ConnectBox, SessionProvider, useSession } from "../../lib/session";
import { generateSyntheticCurve, transitModel, type SyntheticParams } from "../../lib/synthetic";

const DEFAULTS: SyntheticParams = {
  period_days: 10,
  epoch_bjd: 5,
  duration_days: 0.3,
  depth_fraction: 0.01,
  n_points: 2000,
  baseline_days: 60,
  noise_sigma: 0.001,
  seed: 42,
};

function SimulateInner() {
  const { token } = useSession();
  const [params, setParams] = useState<SyntheticParams>(DEFAULTS);
  const [inclination, setInclination] = useState(89.5);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const curve = useMemo(() => generateSyntheticCurve(params), [params]);
  const folded = useMemo(() => {
    const pts = foldToPhase(curve.time, curve.flux, params.period_days, params.epoch_bjd);
    return binFolded(pts, 60);
  }, [curve, params.period_days, params.epoch_bjd]);
  // Live derived numbers (solar host stated; circular orbit stated).
  const kpi = useMemo(() => {
    const a = semiMajorAxisAu(params.period_days, 1.0);
    const k = Math.sqrt(Math.max(params.depth_fraction, 0));
    return {
      a,
      depthPpm: params.depth_fraction * 1e6,
      impact: impactParameter(a, inclination, 1.0),
      duration: circularDurationDays(params.period_days, k, a, inclination, 1.0),
    };
  }, [params.period_days, params.depth_fraction, inclination]);
  const residuals = useMemo(() => {
    const model = transitModel(params);
    return curve.time.map((t, i) => curve.flux[i] - model(t));
  }, [curve, params]);
  const set = (k: keyof SyntheticParams) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setParams((p) => ({ ...p, [k]: Number(e.target.value) }));

  async function submit() {
    if (!token) return;
    setError(null);
    try {
      const res = await submitInlineDataset(
        token,
        { time: curve.time, flux: curve.flux, target_name: curve.target_name },
        { max_signals: 1, snr_floor: 5.0 },
      );
      setJobId(res.job_id);
      setJobStatus(res.status);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function refresh() {
    if (!token || !jobId) return;
    try {
      setJobStatus((await getJob(token, jobId)).status);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main>
      <h1>Simulate</h1>
      <p className="subtitle">
        Synthetic sandbox — every curve here is labelled <Badge /> and every result inherits it.
      </p>
      {!token && (
        <section className="panel">
          <ConnectBox />
        </section>
      )}
      <section className="panel">
        <h2>Injection parameters</h2>
        <div className="row">
          <div>
            <label>Period (d)</label>
            <input type="number" step={0.1} value={params.period_days} onChange={set("period_days")} />
          </div>
          <div>
            <label>Duration (d)</label>
            <input type="number" step={0.01} value={params.duration_days} onChange={set("duration_days")} />
          </div>
          <div>
            <label>Depth (fraction)</label>
            <input type="number" step={0.001} value={params.depth_fraction} onChange={set("depth_fraction")} />
          </div>
          <div>
            <label>Noise σ</label>
            <input type="number" step={0.0005} value={params.noise_sigma} onChange={set("noise_sigma")} />
          </div>
          <div>
            <label>Points</label>
            <input type="number" step={100} value={params.n_points} onChange={set("n_points")} />
          </div>
          <div>
            <label>Baseline (d)</label>
            <input type="number" step={1} value={params.baseline_days} onChange={set("baseline_days")} />
          </div>
          <div>
            <label>Seed</label>
            <input type="number" step={1} value={params.seed} onChange={set("seed")} />
          </div>
          <div>
            <label>Inclination (°)</label>
            <input
              type="number"
              step={0.1}
              value={inclination}
              onChange={(e) => setInclination(Number(e.target.value))}
            />
          </div>
        </div>
        <dl className="numbers-strip" aria-label="derived system numbers">
          <div>
            <dt>{kpi.a.toFixed(4)} AU</dt>
            <dd>semi-major axis (Kepler III, 1 M☉ stated)</dd>
          </div>
          <div>
            <dt>{Math.round(kpi.depthPpm).toLocaleString()} ppm</dt>
            <dd>transit depth</dd>
          </div>
          <div>
            <dt>{Number.isNaN(kpi.duration) ? "no transit" : `${kpi.duration.toFixed(3)} d`}</dt>
            <dd>duration (circular geometry)</dd>
          </div>
          <div>
            <dt>{kpi.impact.toFixed(3)}</dt>
            <dd>impact parameter b</dd>
          </div>
        </dl>
      </section>
      <section className="panel">
        <h2>
          System <span className="badge ai">SYNTHETIC</span>
        </h2>
        <OrbitView
          elements={{
            period_days: params.period_days,
            semi_major_axis_au: kpi.a,
            eccentricity: 0,
            inclination_deg: inclination,
            stellar_radius_rsun: 1.0,
          }}
        />
      </section>
      <section className="panel">
        <h2>
          Preview <span className="badge ai">SYNTHETIC</span>
        </h2>
        <LightCurve x={curve.time} y={curve.flux} title="Injected light curve" xlabel="time (d)" />
        <LightCurve x={curve.time} y={residuals} title="Residuals (curve minus noiseless model)" xlabel="time (d)" />
        <LightCurve
          x={folded.phase}
          y={folded.flux}
          title={`Phase-folded at P=${params.period_days} d (60 bins)`}
          xlabel="phase"
        />
      </section>
      <section className="panel">
        <h2>Submit</h2>
        <button onClick={() => void submit()} disabled={!token}>
          Submit to detection pipeline
        </button>
        {!token && <p className="muted">Connect first to submit.</p>}
        {error && <p className="error">{error}</p>}
      </section>
      {jobId && (
        <section className="panel">
          <h2>Injected job</h2>
          <p className="mono">{jobId}</p>
          <p>
            Status: {jobStatus}{" "}
            <button className="secondary" onClick={() => void refresh()}>
              Refresh
            </button>
          </p>
          <p>
            <Link href="/analyses">Open in Analyses for evidence →</Link>
          </p>
        </section>
      )}
    </main>
  );
}

function Badge() {
  return <span className="badge ai">SYNTHETIC</span>;
}

export default function SimulatePage() {
  return (
    <SessionProvider>
      <SimulateInner />
    </SessionProvider>
  );
}
