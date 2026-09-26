"use client";

/**
 * Server-rendered evidence charts for one completed job.
 *
 * Loads the artifact manifest, then the decimated dataset overview,
 * the binned folded curve and the peak-preserving periodogram for the
 * selected candidate.  Every chart carries its decimation receipt
 * (returned/total/stride) and epistemic badge; a job whose photometry
 * was never stored states that instead of rendering an empty frame.
 * Repeat views are free: the client revalidates with ETags (304).
 */
import { useEffect, useState } from "react";
import LightCurve from "./LightCurve";
import {
  getDataset,
  getFolded,
  getPeriodogram,
  listArtifacts,
  type AnalysisResult,
  type ArtifactManifest,
  type DatasetSeries,
  type FoldedSeries,
  type PeriodogramSeries,
} from "../lib/api";

interface Props {
  token: string;
  jobId: string;
  result: AnalysisResult;
}

function receipt(n_returned: number, n_total: number, stride: number): string {
  return `${n_returned.toLocaleString()} of ${n_total.toLocaleString()} points · stride ${stride}`;
}

export default function EvidenceCharts({ token, jobId, result }: Props) {
  const [manifest, setManifest] = useState<ArtifactManifest | null>(null);
  const [dataset, setDataset] = useState<DatasetSeries | null>(null);
  const [folded, setFolded] = useState<FoldedSeries | null>(null);
  const [pg, setPg] = useState<PeriodogramSeries | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setManifest(null);
    setDataset(null);
    setFolded(null);
    setPg(null);
    const cid = result.candidates.length > 0 ? result.candidates[0].candidate_id : null;
    setSelected(cid);
    async function load() {
      try {
        const m = await listArtifacts(token, jobId);
        if (cancelled) return;
        setManifest(m);
        const jobs: Array<Promise<unknown>> = [];
        if (m.dataset.url) {
          jobs.push(
            getDataset(token, jobId, { max_points: 2000 }).then((d) => {
              if (!cancelled) setDataset(d);
            }),
          );
        }
        if (cid) {
          jobs.push(
            getFolded(token, jobId, cid, 80).then((f) => {
              if (!cancelled) setFolded(f);
            }),
            getPeriodogram(token, jobId, cid, 2000).then((p) => {
              if (!cancelled) setPg(p);
            }),
          );
        }
        await Promise.all(jobs);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [token, jobId, result]);

  async function select(cid: string) {
    setSelected(cid);
    setFolded(null);
    setPg(null);
    setError(null);
    try {
      const [f, p] = await Promise.all([
        getFolded(token, jobId, cid, 80),
        getPeriodogram(token, jobId, cid, 2000),
      ]);
      setFolded(f);
      setPg(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (loading) {
    return (
      <div aria-label="loading evidence charts" style={{ marginTop: 12 }}>
        <div className="skeleton" style={{ height: 200, marginBottom: 8 }} />
        <div className="skeleton" style={{ height: 200 }} />
      </div>
    );
  }

  const cands = manifest?.candidates ?? [];
  const showSelector = cands.length > 1 && selected !== null;

  return (
    <div style={{ marginTop: 8 }}>
      {error && <p className="error">{error}</p>}
      {showSelector && (
        <p>
          <span className="muted">Candidate: </span>
          {cands.map((c) => (
            <button
              key={c.candidate_id}
              className={c.candidate_id === selected ? undefined : "secondary"}
              onClick={() => void select(c.candidate_id)}
              style={{ marginRight: 8 }}
            >
              {c.candidate_id}
            </button>
          ))}
        </p>
      )}
      {dataset ? (
        <>
          <h2 style={{ marginTop: 16 }}>
            Light curve <span className="badge measured">MEASURED</span>
          </h2>
          <LightCurve x={dataset.time} y={dataset.flux} title="Light curve (server, decimated)" xlabel="time" />
          <p className="muted mono" style={{ fontSize: 12 }}>
            {receipt(dataset.n_returned, dataset.n_total, dataset.stride)}
          </p>
        </>
      ) : (
        <p className="muted">No stored photometry for this job — only the evidence travels.</p>
      )}
      {folded && (
        <>
          <h2 style={{ marginTop: 16 }}>
            Folded at {folded.candidate_id}{" "}
            <span className="badge derived">DERIVED</span>
          </h2>
          <LightCurve
            x={folded.phase}
            y={folded.flux}
            title={`Phase-folded at P=${folded.period_days.toFixed(4)} d (${folded.bins} bins)`}
            xlabel="phase"
          />
          <p className="muted mono" style={{ fontSize: 12 }}>
            {folded.bins} bins from {folded.n_total.toLocaleString()} points · epoch {folded.epoch_bjd.toFixed(4)}
          </p>
        </>
      )}
      {pg && (
        <>
          <h2 style={{ marginTop: 16 }}>
            Periodogram <span className="badge measured">MEASURED</span>
          </h2>
          <LightCurve x={pg.periods} y={pg.powers} title="BLS periodogram (peak-preserving)" xlabel="period (d)" />
          <p className="muted mono" style={{ fontSize: 12 }}>
            {receipt(pg.n_returned, pg.n_total, pg.stride)}
            {pg.peak ? ` · peak P=${pg.peak.period_days.toFixed(4)} d, power=${pg.peak.power.toFixed(3)}` : ""}
          </p>
        </>
      )}
    </div>
  );
}
