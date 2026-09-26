/**
 * Minimal typed client for the ASTRAEUS FastAPI layer (P1-H).
 *
 * P3-A: wire shapes (`JobResponse`, `InlineDataset`, …) come from the
 * generated OpenAPI schema (`lib/api-generated.d.ts`, via
 * `npm run gen:api`). Domain shapes (`AnalysisResult`, `CandidateEvidence`)
 * mirror `astraeus/contracts/analysis_result.py` — the API serialises them
 * as untyped dicts, so the vitest suite pins the key paths the UI reads.
 * If the API drifts, `gen:api` + `typecheck` fail rather than the UI lying.
 */
import type { components } from "./api-generated";

export const API_URL =
  process.env.NEXT_PUBLIC_ASTRAEUS_API_URL ?? "http://127.0.0.1:8000";

export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type JobResponse = components["schemas"]["JobResponse"];
export type JobListResponse = components["schemas"]["JobListResponse"];

export type InlineDataset = components["schemas"]["InlineDataset"];

export interface WorkerEvent {
  type: string;
  stage?: string;
  [key: string]: unknown;
}

export interface TlsSummary {
  attempted: boolean;
  n_ran_pass: number;
  n_ran_fail: number;
  n_env_unavailable: number;
  n_not_attempted: number;
  environment_error: string | null;
}

export interface CandidateEvidence {
  candidate_id: string;
  period_days: number | null;
  epoch_bjd: number | null;
  duration_hours: number | null;
  depth_fraction: number | null;
  snr: number | null;
  tls: {
    outcome: string;
    sde: number | null;
    fap: number | null;
    period_days: number | null;
  };
  vetting: { verdict: string; confidence: number | null };
  [key: string]: unknown;
}

export interface AnalysisResult {
  schema_version: string;
  job_id: string;
  target_id: string;
  dataset_id: string;
  status: string;
  candidates: CandidateEvidence[];
  tls: TlsSummary;
  capability_snapshot: Record<string, unknown>;
  provenance: Record<string, unknown> | null;
  warnings: unknown[];
  error: string | null;
  error_kind: string | null;
}

export interface ResultResponse {
  result: AnalysisResult;
  provenance: Record<string, unknown> | null;
}

/** Epistemic classes (PRD §10). Every metric the UI shows carries one. */
export type EpistemicClass = "MEASURED" | "DERIVED" | "INFERRED" | "AI";

export function tlsOutcomeLabel(outcome: string): {
  text: string;
  epistemic: EpistemicClass;
} {
  switch (outcome) {
    case "ran_pass":
      return { text: "TLS confirmed (SDE ≥ 5, period agrees)", epistemic: "MEASURED" };
    case "ran_fail":
      return { text: "TLS rejected the candidate", epistemic: "MEASURED" };
    case "env_unavailable":
      return {
        text: "TLS could not execute — infrastructure failure, not a result",
        epistemic: "DERIVED",
      };
    default:
      return { text: "TLS was not attempted", epistemic: "DERIVED" };
  }
}

/** Parse one SSE `data:` line from `/jobs/{id}/events`. Throws on protocol violations. */
export function parseEventLine(line: string): WorkerEvent | null {
  const text = line.trim();
  if (!text) return null;
  if (!text.startsWith("data:")) throw new Error(`not an SSE data line: ${text.slice(0, 80)}`);
  return JSON.parse(text.slice("data:".length)) as WorkerEvent;
}

async function request<T>(
  apiKey: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${apiKey}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`API ${resp.status} ${path}: ${detail.slice(0, 300)}`);
  }
  return (await resp.json()) as T;
}

export async function exchangeToken(apiKey: string): Promise<string> {
  // POST /auth/token takes the raw API key, not a bearer token.
  const resp = await fetch(`${API_URL}/auth/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!resp.ok) {
    if (resp.status === 401) throw new Error("invalid API key (401)");
    throw new Error(`token exchange failed: ${resp.status}`);
  }
  const body = (await resp.json()) as { access_token: string };
  return body.access_token;
}

export function submitInlineDataset(
  token: string,
  dataset: InlineDataset,
  opts?: { max_signals?: number; snr_floor?: number },
): Promise<JobResponse> {
  return request<JobResponse>(token, "/jobs", {
    method: "POST",
    body: JSON.stringify({
      dataset,
      max_signals: opts?.max_signals ?? 5,
      snr_floor: opts?.snr_floor ?? 7.1,
    }),
  });
}

export function submitTarget(
  token: string,
  name: string,
  mission: string,
  opts?: { max_signals?: number; snr_floor?: number },
): Promise<JobResponse> {
  return request<JobResponse>(token, "/jobs", {
    method: "POST",
    body: JSON.stringify({
      target: { name, mission },
      max_signals: opts?.max_signals ?? 5,
      snr_floor: opts?.snr_floor ?? 7.1,
    }),
  });
}

export function getJob(token: string, jobId: string): Promise<JobResponse> {
  return request<JobResponse>(token, `/jobs/${jobId}`);
}

export function listJobs(token: string, limit = 50): Promise<JobListResponse> {
  return request<JobListResponse>(token, `/jobs?limit=${limit}`);
}

export function getResult(token: string, jobId: string): Promise<ResultResponse> {
  return request<ResultResponse>(token, `/jobs/${jobId}/result`);
}

export function cancelJob(token: string, jobId: string): Promise<JobResponse> {
  return request<JobResponse>(token, `/jobs/${jobId}/cancel`, { method: "POST" });
}

export function eventsUrl(jobId: string): string {
  return `${API_URL}/jobs/${jobId}/events`;
}

// -- artifact arrays (3D-evidence program) ----------------------------------
// Decimated series the charts render.  Every payload carries its
// decimation receipt (n_total/n_returned/stride); ETags make repeat
// views free via 304.

export interface ArtifactRef {
  store: string;
  path: string;
  dtype: string;
  shape: number[];
  checksum: string;
  n_bytes: number;
}

export interface ArtifactLink {
  ref: ArtifactRef | null;
  url: string | null;
}

export interface CandidateArtifactEntry {
  candidate_id: string;
  period_days: number | null;
  periodogram: ArtifactLink;
  folded: ArtifactLink;
  ttv: { n_epochs: number | null; rms_minutes: number | null; url: string | null };
}

export interface ArtifactManifest {
  job_id: string;
  dataset: { dataset_id: string | null; ref: ArtifactRef | null; url: string | null };
  candidates: CandidateArtifactEntry[];
}

export interface DatasetSeries {
  job_id: string;
  dataset_id: string | null;
  n_total: number;
  n_returned: number;
  stride: number;
  time: number[];
  flux: number[];
  flux_err: number[] | null;
  etag: string;
}

export interface PeriodogramSeries {
  job_id: string;
  candidate_id: string;
  n_total: number;
  n_returned: number;
  stride: number;
  periods: number[];
  powers: number[];
  peak: { period_days: number; power: number } | null;
}

export interface FoldedSeries {
  job_id: string;
  candidate_id: string;
  period_days: number;
  epoch_bjd: number;
  bins: number;
  n_total: number;
  phase: number[];
  flux: number[];
  counts: number[];
}

export interface TtvSeries {
  job_id: string;
  candidate_id: string;
  n_epochs: number;
  rms_minutes: number | null;
  residuals_min: number[];
}

const seriesEtags = new Map<string, string>();
const seriesCache = new Map<string, unknown>();

async function fetchSeries<T>(token: string, path: string): Promise<T> {
  const url = `${API_URL}${path}`;
  const headers: Record<string, string> = { authorization: `Bearer ${token}` };
  const tag = seriesEtags.get(url);
  if (tag) headers["if-none-match"] = tag;
  const resp = await fetch(url, { headers });
  if (resp.status === 304) {
    const hit = seriesCache.get(url);
    if (hit !== undefined) return hit as T;
    // Cache lost (reload): fall through with a clean re-fetch.
    const retry = await fetch(url, { headers: { authorization: `Bearer ${token}` } });
    if (!retry.ok) throw new Error(`API ${retry.status} ${path}`);
    return readSeries<T>(url, retry);
  }
  if (!resp.ok) {
    throw new Error(`API ${resp.status} ${path}: ${(await resp.text()).slice(0, 200)}`);
  }
  return readSeries<T>(url, resp);
}

async function readSeries<T>(url: string, resp: Response): Promise<T> {
  const tag = resp.headers.get("etag");
  const data = (await resp.json()) as T;
  if (tag) {
    seriesEtags.set(url, tag);
    seriesCache.set(url, data);
  }
  return data;
}

export function listArtifacts(token: string, jobId: string): Promise<ArtifactManifest> {
  return fetchSeries<ArtifactManifest>(token, `/jobs/${jobId}/artifacts`);
}

export function getDataset(
  token: string,
  jobId: string,
  opts?: { max_points?: number; t_min?: number; t_max?: number },
): Promise<DatasetSeries> {
  const q = new URLSearchParams({ type: "dataset" });
  if (opts?.max_points !== undefined) q.set("max_points", String(opts.max_points));
  if (opts?.t_min !== undefined) q.set("t_min", String(opts.t_min));
  if (opts?.t_max !== undefined) q.set("t_max", String(opts.t_max));
  return fetchSeries<DatasetSeries>(token, `/jobs/${jobId}/artifacts/data?${q}`);
}

export function getPeriodogram(
  token: string,
  jobId: string,
  candidateId: string,
  max_points = 2000,
): Promise<PeriodogramSeries> {
  const q = new URLSearchParams({ type: "periodogram", candidate: candidateId, max_points: String(max_points) });
  return fetchSeries<PeriodogramSeries>(token, `/jobs/${jobId}/artifacts/data?${q}`);
}

export function getFolded(
  token: string,
  jobId: string,
  candidateId: string,
  bins = 80,
): Promise<FoldedSeries> {
  const q = new URLSearchParams({ type: "folded", candidate: candidateId, bins: String(bins) });
  return fetchSeries<FoldedSeries>(token, `/jobs/${jobId}/artifacts/data?${q}`);
}

export function getTtv(token: string, jobId: string, candidateId: string): Promise<TtvSeries> {
  const q = new URLSearchParams({ type: "ttv", candidate: candidateId });
  return fetchSeries<TtvSeries>(token, `/jobs/${jobId}/artifacts/data?${q}`);
}

/**
 * Auth-capable SSE reader for `/jobs/{id}/events`.
 *
 * Native EventSource cannot send an Authorization header, so the previous
 * EventSource path silently failed against the protected route. This uses
 * fetch + a line reader (same pattern as explainResult), with identical
 * `parseEventLine` semantics. Callers keep their polling backstop.
 */
export async function streamJobEvents(
  token: string,
  jobId: string,
  onEvent: (ev: WorkerEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(eventsUrl(jobId), {
    headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" },
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`events ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      for (const line of block.split("\n")) {
        const ev = parseEventLine(line);
        if (ev) onEvent(ev);
      }
    }
    if (signal?.aborted) break;
  }
}

export interface CopilotEvent {
  kind: "evidence" | "text" | "error" | "done";
  digest?: string;
  delta?: string;
  detail?: string;
  error_kind?: string;
}

/** Stream an evidence-grounded explanation. Calls onEvent per SSE record. */
export async function explainResult(
  token: string,
  result: AnalysisResult,
  question: string,
  provider: string | null,
  onEvent: (ev: CopilotEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_URL}/copilot/explain`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      result,
      question,
      provider: provider === "none" ? null : provider,
    }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`copilot ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n\n");
    buf = lines.pop() ?? "";
    for (const chunk of lines) {
      for (const line of chunk.split("\n")) {
        const ev = parseEventLine(line);
        if (ev) onEvent(ev as unknown as CopilotEvent);
      }
    }
  }
}

/** Parse a two-column (time,flux[,flux_err]) CSV upload into an inline dataset. */
export function parseLightCurveCsv(text: string, targetName: string): InlineDataset {
  const time: number[] = [];
  const flux: number[] = [];
  const err: number[] = [];
  let hasErr = false;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const cells = line.split(/[,\s;]+/).filter(Boolean);
    if (cells.length < 2) continue;
    const t = Number(cells[0]);
    const f = Number(cells[1]);
    if (!Number.isFinite(t) || !Number.isFinite(f)) continue;
    // Skip a header row that slipped through (non-numeric already skips).
    time.push(t);
    flux.push(f);
    if (cells.length >= 3 && Number.isFinite(Number(cells[2]))) {
      err.push(Number(cells[2]));
      hasErr = true;
    } else {
      err.push(0);
    }
  }
  if (time.length < 10) {
    throw new Error(`only ${time.length} valid rows — need at least 10 data points`);
  }
  return {
    time,
    flux,
    flux_err: hasErr ? err : null,
    target_name: targetName || "uploaded-curve",
  };
}
