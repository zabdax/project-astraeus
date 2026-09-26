"use client";

/**
 * P3-C Analyses route: durable jobs, not session state.
 * List (owner-scoped by the store query) → detail with evidence summary,
 * provenance, warnings → download / cancel. Restoring a job means viewing
 * its record; re-running means submitting again from Investigate.
 */
import { useCallback, useEffect, useState } from "react";
import EvidenceCharts from "../../components/EvidenceCharts";
import {
  cancelJob,
  getJob,
  getResult,
  listJobs,
  tlsOutcomeLabel,
  type AnalysisResult,
  type JobResponse,
} from "../../lib/api";
import { ConnectBox, SessionProvider, useSession } from "../../lib/session";

function fmt(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function AnalysesInner() {
  const { token } = useSession();
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<JobResponse | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    setError(null);
    try {
      const body = await listJobs(token, 50);
      setJobs(body.jobs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [token]);

  useEffect(() => {
    setJobs([]);
    setSelected(null);
    setDetail(null);
    setResult(null);
    if (token) void refresh();
  }, [token, refresh]);

  async function open(jobId: string) {
    if (!token) return;
    setError(null);
    setResult(null);
    try {
      setSelected(jobId);
      const j = await getJob(token, jobId);
      setDetail(j);
      if (j.status === "COMPLETED") {
        setResult((await getResult(token, jobId)).result);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function cancel() {
    if (!token || !selected) return;
    try {
      const j = await cancelJob(token, selected);
      setDetail(j);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function download() {
    if (!result || !detail) return;
    const blob = new Blob([JSON.stringify({ job: detail, result }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `astraeus-analysis-${detail.job_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!token) {
    return (
      <main>
        <h1>Analyses</h1>
        <p className="subtitle">Durable results live here — connect to list your jobs.</p>
        <section className="panel">
          <ConnectBox />
        </section>
      </main>
    );
  }

  return (
    <main>
      <h1>Analyses</h1>
      <p className="subtitle">
        Every job persists with its result and provenance.{" "}
        <button className="secondary" onClick={() => void refresh()}>
          Refresh
        </button>
      </p>
      {error && <p className="error">{error}</p>}
      <div className="row" style={{ alignItems: "flex-start" }}>
        <section className="panel" style={{ flex: "1 1 300px" }}>
          <h2>Jobs ({jobs.length})</h2>
          {jobs.length === 0 && <p className="muted">No jobs yet — run one from Investigate.</p>}
          {jobs.map((j) => (
            <div key={j.job_id} style={{ marginBottom: 8 }}>
              <button
                className={selected === j.job_id ? undefined : "secondary"}
                onClick={() => void open(j.job_id)}
                style={{ marginTop: 0, width: "100%", textAlign: "left" }}
              >
                <span className={`status-dot ${j.status.toLowerCase()}`} />
                <span className="mono">{j.target_name}</span> · {j.status}
              </button>
              <div className="muted mono">{j.job_id.slice(0, 8)} · {j.updated_at}</div>
            </div>
          ))}
        </section>
        <section className="panel" style={{ flex: "2 1 420px" }}>
          <h2>Detail</h2>
          {!detail && <p className="muted">Select a job.</p>}
          {detail && (
            <>
              <p>
                <span className={`status-dot ${detail.status.toLowerCase()}`} />
                <span className="mono">{detail.job_id}</span>
              </p>
              <p className="muted">
                {detail.target_name} · stage {detail.stage} · iteration{" "}
                {detail.iteration ?? "—"}/{detail.max_iterations ?? "—"}
              </p>
              {detail.error && <p className="error">{detail.error} ({detail.error_kind})</p>}
              {!["COMPLETED", "FAILED", "CANCELLED"].includes(detail.status) && (
                <button className="danger" onClick={() => void cancel()}>
                  Cancel
                </button>
              )}
              {result && (
                <>
                  <table className="evidence">
                    <thead>
                      <tr>
                        <th>Candidate</th>
                        <th>Period (d)</th>
                        <th>SNR</th>
                        <th>TLS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.candidates.length === 0 && (
                        <tr>
                          <td colSpan={4} className="muted">
                            No candidates — measured negative (TLS ran{" "}
                            {result.tls.n_ran_pass + result.tls.n_ran_fail}×).
                          </td>
                        </tr>
                      )}
                      {result.candidates.map((c) => (
                        <tr key={c.candidate_id}>
                          <td className="mono">{c.candidate_id}</td>
                          <td>{fmt(c.period_days)}</td>
                          <td>{fmt(c.snr, 2)}</td>
                          <td>
                            {tlsOutcomeLabel(c.tls.outcome).text}
                            {c.tls.sde !== null && (
                              <span className="muted"> · SDE {fmt(c.tls.sde, 2)}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {detail && token && selected && (
                    <EvidenceCharts token={token} jobId={selected} result={result} />
                  )}
                  <details className="provenance">
                    <summary>Provenance</summary>                   <pre className="dump">
                      {JSON.stringify(
                        {
                          dataset_id: result.dataset_id,
                          capability_snapshot: result.capability_snapshot,
                          tls_summary: result.tls,
                          warnings: result.warnings,
                          provenance: result.provenance,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                  <button className="secondary" onClick={download}>
                    Download analysis JSON
                  </button>
                </>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}

export default function AnalysesPage() {
  return (
    <SessionProvider>
      <AnalysesInner />
    </SessionProvider>
  );
}
