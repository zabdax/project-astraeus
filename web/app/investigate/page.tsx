"use client";

/**
 * P2-B vertical slice: Investigate (minimal honest UI).
 *
 * One real user journey against the P1-H API over the P2-A backend slice:
 * connect → data (target fetch or CSV upload) → run → measured progress
 * (SSE) → evidence with epistemic labels (PRD §10) → provenance →
 * download. No planet probability is invented anywhere; every number
 * carries MEASURED / DERIVED and TLS states truthfully whether it ran.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_URL,
  cancelJob,
  eventsUrl,
  exchangeToken,
  getJob,
  getResult,
  parseEventLine,
  parseLightCurveCsv,
  submitInlineDataset,
  submitTarget,
  tlsOutcomeLabel,
  type AnalysisResult,
  type EpistemicClass,
  type InlineDataset,
  type JobResponse,
  type WorkerEvent,
} from "../../lib/api";

type Phase = "connect" | "data" | "running" | "done";

function Badge({ epistemic }: { epistemic: EpistemicClass }) {
  return <span className={`badge ${epistemic.toLowerCase()}`}>{epistemic}</span>;
}

function fmt(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

export default function InvestigatePage() {
  const [phase, setPhase] = useState<Phase>("connect");
  const [apiKey, setApiKey] = useState("");
  const [token, setToken] = useState<string | null>(null);
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
  const esRef = useRef<EventSource | null>(null);

  const stopStreams = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (esRef.current) esRef.current.close();
    pollRef.current = null;
    esRef.current = null;
  }, []);

  useEffect(() => stopStreams, [stopStreams]);

  async function connect() {
    setError(null);
    try {
      const t = await exchangeToken(apiKey);
      setToken(t);
      setPhase("data");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

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
        setError("upload a CSV light curve first");
        return;
      }
      setJob(res);
      setPhase("running");
      watchJob(res.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function watchJob(jobId: string) {
    if (!token) return;
    const t = token;
    // SSE trail (replay-then-live) for honest progress; polling as the
    // terminal-state backstop so a dropped stream can never stick the UI.
    try {
      const es = new EventSource(eventsUrl(jobId));
      esRef.current = es;
      es.onmessage = (msg) => {
        try {
          const ev = parseEventLine(`data: ${msg.data}`);
          if (ev) setEvents((prev) => [...prev, ev]);
        } catch {
          /* protocol violation surfaces via polling, not a stuck UI */
        }
      };
      es.onerror = () => es.close();
    } catch {
      /* EventSource unavailable — polling below still completes the job */
    }
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
            setError(j.error ?? `job ${j.status.toLowerCase()}`);
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

  return (
    <main>
      <h1>ASTRAEUS — Investigate</h1>
      <p className="subtitle">
        Minimal honest UI over the transit-search API (P2-B slice). API:{" "}
        <span className="mono">{API_URL}</span>
      </p>

      {/* ---- 1. Connect ---- */}
      <section className="panel">
        <h2>1 · Connect</h2>
        {token ? (
          <p className="muted">Authenticated — token held in memory only, never stored.</p>
        ) : (
          <div className="row">
            <div>
              <label htmlFor="apikey">API key (single-user deployment)</label>
              <input
                id="apikey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="ASTRAEUS_API_KEY value"
              />
            </div>
            <div style={{ alignSelf: "end", flexGrow: 0 }}>
              <button onClick={connect} disabled={!apiKey}>
                Connect
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ---- 2. Data ---- */}
      <section className="panel">
        <h2>2 · Data — one job consumes one dataset</h2>
        <div className="row">
          <div>
            <label htmlFor="source">Source</label>
            <select id="source" value={source} onChange={(e) => setSource(e.target.value as "target" | "csv")}>
              <option value="target">Real fetch (MAST / archive)</option>
              <option value="csv">CSV upload (time,flux[,flux_err])</option>
            </select>
          </div>
          {source === "target" ? (
            <>
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
            </>
          ) : (
            <div>
              <label htmlFor="csv">Light-curve file</label>
              <input
                id="csv"
                type="file"
                accept=".csv,.txt"
                onChange={(e) => onCsvFile(e.target.files?.[0])}
              />
              {dataset && (
                <p className="muted">
                  {csvName}: {dataset.time.length.toLocaleString()} points, baseline{" "}
                  {fmt(dataset.time[dataset.time.length - 1] - dataset.time[0], 1)} d
                </p>
              )}
            </div>
          )}
        </div>
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
          <div style={{ alignSelf: "end", flexGrow: 0 }}>
            <button onClick={submit} disabled={!token || phase === "running"}>
              Run search
            </button>
          </div>
        </div>
        {error && phase !== "running" && <p className="error">{error}</p>}
      </section>

      {/* ---- 3. Progress ---- */}
      {(phase === "running" || job) && (
        <section className="panel">
          <h2>3 · Progress — measured, not a bar</h2>
          {job && (
            <p>
              <span className={`status-dot ${job.status.toLowerCase()}`} />
              <span className="mono">{job.job_id}</span> · {job.status} · stage {job.stage}
              {job.iteration !== null && job.max_iterations !== null
                ? ` · iteration ${job.iteration}/${job.max_iterations}`
                : ""}
            </p>
          )}
          {phase === "running" && !terminal && (
            <button className="danger" onClick={cancel}>
              Cancel (kills the process tree)
            </button>
          )}
          <div className="eventlog" aria-label="job events">
            {events.length === 0 && <div className="muted">waiting for first event…</div>}
            {events.slice(-30).map((ev, i) => (
              <div key={i} className="mono muted">
                {ev.type}
                {typeof ev.iteration === "number" ? ` #${ev.iteration}` : ""}
                {typeof ev.stage === "string" ? ` · ${ev.stage}` : ""}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---- 4. Evidence ---- */}
      {phase === "done" && result && (
        <section className="panel">
          <h2>4 · Evidence — never a planet probability</h2>
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
                  <th>Period (d) <Badge epistemic="MEASURED" /></th>
                  <th>Depth <Badge epistemic="MEASURED" /></th>
                  <th>SNR <Badge epistemic="MEASURED" /></th>
                  <th>TLS <Badge epistemic="MEASURED" /></th>
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

          <details className="provenance">
            <summary>Provenance — reproduce this run from its own record</summary>
            <pre className="dump">
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
          <div className="row">
            <div style={{ flexGrow: 0 }}>
              <button className="secondary" onClick={download}>
                Download result JSON
              </button>
            </div>
          </div>
        </section>
      )}
      {phase === "done" && !result && error && <p className="error">{error}</p>}

      <section className="panel">
        <h2>What this page will not show</h2>
        <ol className="steps">
          <li>No “planet probability” — the engine computes no such quantity.</li>
          <li>No AI interpretation in this slice — copilot lands in P3-G, labelled AI.</li>
          <li>No inference section — MCMC wiring is Phase 4 work; the field stays null.</li>
        </ol>
      </section>
    </main>
  );
}
