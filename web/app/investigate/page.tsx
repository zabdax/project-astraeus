"use client";

/**
 * Investigate: the blind search as a four-step workspace.
 * Connect → data → run → evidence. Numbers carry epistemic badges;
 * TLS states truthfully whether it ran; nothing here invents a planet.
 *
 * Session is shared (memory-only bearer token). Job progress streams
 * over authenticated fetch-SSE with the 1.5s poll as backstop, so a
 * dropped stream never sticks the UI in a terminal state.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ChartLineUp, Database, DownloadSimple, Key, Play, X } from "@phosphor-icons/react";
import CopilotPanel from "../../components/CopilotPanel";
import EvidenceCharts from "../../components/EvidenceCharts";
import LightCurve from "../../components/LightCurve";
import {
  API_URL,
  cancelJob,
  getJob,
  getResult,
  parseEventLine,
  parseLightCurveCsv,
  streamJobEvents,
  submitInlineDataset,
  submitTarget,
  tlsOutcomeLabel,
  type AnalysisResult,
  type EpistemicClass,
  type InlineDataset,
  type JobResponse,
  type WorkerEvent,
} from "../../lib/api";
import { ConnectBox, SessionProvider, useSession } from "../../lib/session";

type Phase = "connect" | "data" | "running" | "done";

function Badge({ epistemic }: { epistemic: EpistemicClass }) {
  return <span className={`badge ${epistemic.toLowerCase()}`}>{epistemic}</span>;
}

function fmt(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function StepHead({ n, icon: Icon, title }: { n: number; icon: typeof Key; title: string }) {
  return (
    <h2 className="step-head">
      <span className="step-n" aria-hidden>
        {n}
      </span>
      <Icon size={16} weight="duotone" aria-hidden />
      {title}
    </h2>
  );
}

function progressOf(job: JobResponse | null): number {
  if (!job) return 0;
  const j = job as JobResponse & { progress?: number | null; iteration?: number | null; max_iterations?: number | null };
  if (typeof j.progress === "number" && Number.isFinite(j.progress)) {
    return Math.min(1, Math.max(0, j.progress > 1 ? j.progress / 100 : j.progress));
  }
  if (typeof j.iteration === "number" && typeof j.max_iterations === "number" && j.max_iterations > 0) {
    return Math.min(1, Math.max(0, j.iteration / j.max_iterations));
  }
  return 0;
}

function InvestigateInner() {
  const { token } = useSession();
  const [phase, setPhase] = useState<Phase>("connect");
  const [error, setError] = useState<string | null>(null);

  const [source, setSource] = useState<"target" | "csv">("target");
  const [targetName, setTargetName] = useState("Kepler-90");
  const [mission, setMission] = useState("Kepler");
  const [dataset, setDataset] = useState<InlineDataset | null>(null);
  const [csvName, setCsvName] = useState("");
  const [maxSignals, setMaxSignals] = useState(5);
  const [snrFloor, setSnrFloor] = useState(7.1);

  const [job, setJob] = useState<JobResponse | null>(null);
  const [events, setEvents] = useState<WorkerEvent[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [resultProvenance, setResultProvenance] = useState<Record<string, unknown> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stopStreams = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    abortRef.current?.abort();
    pollRef.current = null;
    abortRef.current = null;
  }, []);

  useEffect(() => stopStreams, [stopStreams]);
  useEffect(() => {
    if (token && phase === "connect") setPhase("data");
    if (!token) {
      stopStreams();
      setPhase("connect");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function onCsvFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      const text = await file.text();
      const ds = parseLightCurveCsv(text, file.name.replace(/\.[^.]+$/, ""));
      setDataset(ds);
      setCsvName(file.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDataset(null);
    }
  }

  async function submit() {
    if (!token) return;
    setError(null);
    setEvents([]);
    setResult(null);
    setResultProvenance(null);
    try {
      const res =
        source === "target"
          ? await submitTarget(token, targetName.trim(), mission, { max_signals: maxSignals, snr_floor: snrFloor })
          : dataset
            ? await submitInlineDataset(token, dataset, { max_signals: maxSignals, snr_floor: snrFloor })
            : null;
      if (!res) {
        setError("Upload a CSV light curve first, then run the search.");
        return;
      }
      setJob(res);
      setPhase("running");
      watchJob(token, res.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function watchJob(t: string, jobId: string) {
    stopStreams();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    // Authenticated stream: EventSource cannot send a Bearer header, so
    // fetch-SSE carries the token. Failures fall through to polling.
    void streamJobEvents(
      t,
      jobId,
      (ev) => {
        // Guard: only well-formed worker events reach the log.
        try {
          const check = parseEventLine(`data: ${JSON.stringify(ev)}`);
          if (check) setEvents((prev) => [...prev.slice(-60), ev]);
        } catch {
          /* protocol violation surfaces via polling, not a stuck UI */
        }
      },
      ctrl.signal,
    ).catch(() => {
      /* polling below still completes the job */
    });
    pollRef.current = setInterval(async () => {
      try {
        const j = await getJob(t, jobId);
        setJob(j);
        if (j.status === "COMPLETED" || j.status === "FAILED" || j.status === "CANCELLED") {
          stopStreams();
          if (j.status === "COMPLETED") {
            const r = await getResult(t, jobId);
            setResult(r.result);
            setResultProvenance(r.provenance);
          } else {
            setError(j.error ?? `Job ${j.status.toLowerCase()}. Check the API log for the reason.`);
          }
          setPhase("done");
        }
      } catch (e) {
        stopStreams();
        setError(e instanceof Error ? e.message : String(e));
        setPhase("done");
      }
    }, 1500);
  }

  async function cancel() {
    if (!token || !job) return;
    try {
      const j = await cancelJob(token, job.job_id);
      setJob(j);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function download() {
    if (!result) return;
    const blob = new Blob([JSON.stringify({ result, provenance: resultProvenance }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `astraeus-result-${result.job_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const terminal = job !== null && ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status);
  const running = phase === "running" && !terminal;

  return (
    <main>
      <p className="eyebrow">Blind search</p>
      <h1>Investigate a light curve</h1>
      <p className="subtitle">
        One job, one dataset, measured progress. API: <span className="mono">{API_URL}</span>
      </p>

      <div className="workspace">
        <div className="rail">
          <section className="panel">
            <StepHead n={1} icon={Key} title="Connect" />
            <ConnectBox />
          </section>

          <section className="panel">
            <StepHead n={2} icon={Database} title="Data" />
            <label htmlFor="source">Source</label>
            <select id="source" value={source} onChange={(e) => setSource(e.target.value as "target" | "csv")}>
              <option value="target">Real fetch (MAST / archive)</option>
              <option value="csv">CSV upload (time,flux[,flux_err])</option>
            </select>
            {source === "target" ? (
              <div className="row" style={{ marginTop: 10 }}>
                <div>
                  <label htmlFor="target">Target</label>
                  <input id="target" type="text" value={targetName} onChange={(e) => setTargetName(e.target.value)} />
                </div>
                <div>
                  <label htmlFor="mission">Mission</label>
                  <select id="mission" value={mission} onChange={(e) => setMission(e.target.value)}>
                    <option>Kepler</option>
                    <option>K2</option>
                    <option>TESS</option>
                  </select>
                </div>
              </div>
            ) : (
              <>
                <div style={{ marginTop: 10 }}>
                  <label htmlFor="csv">Light-curve file</label>
                  <input id="csv" type="file" accept=".csv,.txt" onChange={(e) => onCsvFile(e.target.files?.[0])} />
                </div>
                {dataset && (
                  <p className="muted">
                    {csvName}: {dataset.time.length.toLocaleString()} points, baseline{" "}
                    {fmt(dataset.time[dataset.time.length - 1] - dataset.time[0], 1)} d
                  </p>
                )}
              </>
            )}
          </section>

          <section className="panel">
            <StepHead n={3} icon={Play} title="Run" />
            <div className="row">
              <div>
                <label htmlFor="maxsignals">Max signals (1–10)</label>
                <input
                  id="maxsignals"
                  type="number"
                  min={1}
                  max={10}
                  value={maxSignals}
                  onChange={(e) => setMaxSignals(Number(e.target.value))}
                />
              </div>
              <div>
                <label htmlFor="snrfloor">SNR floor</label>
                <input
                  id="snrfloor"
                  type="number"
                  step={0.1}
                  value={snrFloor}
                  onChange={(e) => setSnrFloor(Number(e.target.value))}
                />
              </div>
            </div>
            <button onClick={submit} disabled={!token || running} style={{ width: "100%" }}>
              {running ? "Searching…" : "Run search"}
            </button>
            {!token && <p className="muted">Connect first to run.</p>}
          </section>
        </div>

        <div className="results">
          {(job || running) && (
            <section className="panel">
              <StepHead n={4} icon={ChartLineUp} title="Evidence" />
              {job && (
                <p>
                  <span className={`status-dot ${job.status.toLowerCase()}`} />
                  <span className="mono">{job.job_id}</span>
                  <span className="muted">
                    {" "}
                    · {job.status} · {job.stage}
                    {job.iteration !== null && job.max_iterations !== null
                      ? ` · iteration ${job.iteration}/${job.max_iterations}`
                      : ""}
                  </span>
                </p>
              )}
              {(running || (job && !terminal)) && (
                <>
                  <div
                    className="run-meter"
                    role="progressbar"
                    aria-label={`search progress: ${job?.stage ?? "starting"}`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(progressOf(job) * 100)}
                    style={{ ["--p" as string]: progressOf(job) }}
                  >
                    <span />
                  </div>
                  <p className="run-phase">
                    {job?.stage ?? "starting"}
                    {typeof (job as { iteration?: unknown })?.iteration === "number"
                      ? ` · iteration ${(job as { iteration: number }).iteration}`
                        + (typeof (job as { max_iterations?: unknown })?.max_iterations === "number"
                          ? `/${(job as { max_iterations: number }).max_iterations}`
                          : "")
                      : ""}
                  </p>
                </>
              )}
              {running && !terminal && (
                <button className="danger" onClick={cancel}>
                  <X size={14} weight="bold" aria-hidden style={{ verticalAlign: "-2px", marginRight: 6 }} />
                  Cancel (kills the process tree)
                </button>
              )}
              {running && !result && (
                <div aria-label="loading results" style={{ marginTop: 12 }}>
                  <div className="skeleton" style={{ height: 34, marginBottom: 8 }} />
                  <div className="skeleton" style={{ height: 34, marginBottom: 8 }} />
                  <div className="skeleton" style={{ height: 34 }} />
                </div>
              )}
              <div className="eventlog" aria-label="job events">
                {events.length === 0 && <div>waiting for first event…</div>}
                {events.slice(-30).map((ev, i) => (
                  <div key={i}>
                    {ev.type}
                    {typeof ev.iteration === "number" ? ` #${ev.iteration}` : ""}
                    {typeof ev.stage === "string" ? ` · ${ev.stage}` : ""}
                  </div>
                ))}
              </div>
              {error && phase !== "data" && <p className="error">{error}</p>}
            </section>
          )}

          {source === "csv" && dataset && !job && (
            <section className="panel">
              <h2>Uploaded curve</h2>
              <LightCurve x={dataset.time} y={dataset.flux} title="Uploaded light curve" xlabel="time" />
            </section>
          )}

          {phase === "done" && result && (
            <section className="panel">
              <h2>Candidates — never a planet probability</h2>
              {result.candidates.length === 0 ? (
                <p>
                  No candidates found.{" "}
                  <span className="muted">
                    TLS ran {result.tls.n_ran_pass + result.tls.n_ran_fail}×
                    {result.tls.n_env_unavailable > 0
                      ? `, unavailable ${result.tls.n_env_unavailable}× — treat with suspicion`
                      : ""}
                    . An empty list on a COMPLETED job is a measured negative, not a broken run.
                  </span>
                </p>
              ) : (
                <table className="evidence">
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th>
                        Period (d) <Badge epistemic="MEASURED" />
                      </th>
                      <th>
                        Depth <Badge epistemic="MEASURED" />
                      </th>
                      <th>
                        SNR <Badge epistemic="MEASURED" />
                      </th>
                      <th>
                        TLS <Badge epistemic="MEASURED" />
                      </th>
                      <th>Vetting</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.candidates.map((c) => {
                      const tls = tlsOutcomeLabel(c.tls.outcome);
                      return (
                        <tr key={c.candidate_id}>
                          <td className="mono">{c.candidate_id}</td>
                          <td>{fmt(c.period_days)}</td>
                          <td>{fmt(c.depth_fraction, 6)}</td>
                          <td>{fmt(c.snr, 2)}</td>
                          <td>
                            {tls.text} <Badge epistemic={tls.epistemic} />
                            {c.tls.sde !== null && <span className="muted"> · SDE {fmt(c.tls.sde, 2)}</span>}
                          </td>
                          <td>
                            {c.vetting.verdict} <Badge epistemic="DERIVED" />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              {result && token && (
                <EvidenceCharts token={token} jobId={result.job_id} result={result} />
              )}

              <details className="provenance">
                <summary>Provenance — reproduce this run from its own record</summary>                <pre className="dump">
                  {JSON.stringify(
                    {
                      dataset_id: result.dataset_id,
                      capability_snapshot: result.capability_snapshot,
                      tls_summary: result.tls,
                      warnings: result.warnings,
                      provenance: resultProvenance,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <button className="secondary" onClick={download}>
                <DownloadSimple size={14} weight="bold" aria-hidden style={{ verticalAlign: "-2px", marginRight: 6 }} />
                Download result JSON
              </button>
            </section>
          )}
          {phase === "done" && !result && error && <p className="error">{error}</p>}
        </div>
      </div>

      <section className="panel">
        <h2>What this page will not show</h2>
        <ol className="steps">
          <li>No “planet probability” — the engine computes no such quantity.</li>
          <li>No AI interpretation inline — the copilot panel below is labelled AI, verify against the table.</li>
          <li>No inference section — MCMC wiring is Phase 4 work; the field stays null.</li>
        </ol>
      </section>

      {phase === "done" && result && token && <CopilotPanel token={token} result={result} />}
    </main>
  );
}

export default function InvestigatePage() {
  return (
    <SessionProvider>
      <InvestigateInner />
    </SessionProvider>
  );
}
