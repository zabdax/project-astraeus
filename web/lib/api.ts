/**
 * Minimal typed client for the ASTRAEUS FastAPI layer (P1-H).
 *
 * P2-B scope note: this client is hand-written for the vertical slice.
 * P3-A replaces it with a client generated from the API's OpenAPI schema.
 * Field names mirror `astraeus/api/schemas.py` and
 * `astraeus/contracts/analysis_result.py` exactly — if the API drifts,
 * the vitest suite (`lib/api.test.ts`) fails rather than the UI lying.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_ASTRAEUS_API_URL ?? "http://127.0.0.1:8000";

export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface JobResponse {
  job_id: string;
  owner_id: string;
  target_name: string;
  mission: string | null;
  status: JobStatus | string;
  stage: string;
  progress: number;
  iteration: number | null;
  max_iterations: number | null;
  n_candidates: number | null;
  result_id: string | null;
  error: string | null;
  error_kind: string | null;
  created_at: string;
  updated_at: string;
}

export interface InlineDataset {
  time: number[];
  flux: number[];
  flux_err?: number[] | null;
  target_name: string;
}

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

export function getResult(token: string, jobId: string): Promise<ResultResponse> {
  return request<ResultResponse>(token, `/jobs/${jobId}/result`);
}

export function cancelJob(token: string, jobId: string): Promise<JobResponse> {
  return request<JobResponse>(token, `/jobs/${jobId}/cancel`, { method: "POST" });
}

export function eventsUrl(jobId: string): string {
  return `${API_URL}/jobs/${jobId}/events`;
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
