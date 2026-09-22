"use client";

/**
 * P3-G copilot panel: evidence-grounded chat, strictly labelled.
 * Everything rendered here is AI-INTERPRETED prose — verify numbers
 * against the evidence table above. Streams from POST /copilot/explain.
 */
import { useRef, useState } from "react";
import { explainResult, type AnalysisResult, type CopilotEvent } from "../lib/api";

interface Props {
  token: string;
  result: AnalysisResult;
}

function storedProvider(): string | null {
  try {
    const raw = localStorage.getItem("astraeus-byok");
    if (!raw) return null;
    return (JSON.parse(raw) as { provider?: string }).provider ?? null;
  } catch {
    return null;
  }
}

export default function CopilotPanel({ token, result }: Props) {
  const [question, setQuestion] = useState("Explain these results for a non-expert.");
  const [answer, setAnswer] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function ask() {
    setError(null);
    setAnswer("");
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await explainResult(token, result, question, storedProvider(), (ev: CopilotEvent) => {
        if (ev.kind === "text" && ev.delta) setAnswer((prev) => (prev ?? "") + ev.delta);
        if (ev.kind === "error") setError(ev.detail ?? ev.error_kind ?? "copilot error");
      }, ctrl.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="panel">
      <h2>
        Copilot <span className="badge ai">AI-INTERPRETED</span>
      </h2>
      <p className="muted">
        Prose over the evidence above — verify every number against the table. Configure a
        provider in Settings; with none configured the server says so instead of inventing.
      </p>
      <label htmlFor="copilot-q">Question</label>
      <input id="copilot-q" type="text" value={question} onChange={(e) => setQuestion(e.target.value)} />
      <div className="row">
        <div style={{ flexGrow: 0 }}>
          <button onClick={() => void ask()} disabled={running}>
            {running ? "Asking…" : "Ask"}
          </button>
        </div>
        {running && (
          <div style={{ flexGrow: 0 }}>
            <button className="secondary" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          </div>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {answer !== null && answer !== "" && <pre className="dump">{answer}</pre>}
    </section>
  );
}
