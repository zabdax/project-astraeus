/**
 * P2-B client tests: the UI must never lie about the API contract.
 * Field paths asserted here mirror the P2-A slice result shape
 * (`AnalysisResult.to_dict` + `TlsSummary` + per-candidate `TlsEvidence`).
 */
import { describe, expect, it, vi } from "vitest";
import {
  getDataset,
  getFolded,
  listArtifacts,
  parseEventLine,
  parseLightCurveCsv,
  streamJobEvents,
  tlsOutcomeLabel,
} from "./api";

describe("tlsOutcomeLabel", () => {
  it("labels a TLS pass as measured evidence", () => {
    expect(tlsOutcomeLabel("ran_pass")).toEqual({
      text: expect.stringContaining("confirmed"),
      epistemic: "MEASURED",
    });
  });

  it("labels infrastructure failure as derived, never a result", () => {
    const label = tlsOutcomeLabel("env_unavailable");
    expect(label.epistemic).toBe("DERIVED");
    expect(label.text).toMatch(/infrastructure failure/);
  });

  it("never invents a planet probability", () => {
    for (const outcome of ["ran_pass", "ran_fail", "env_unavailable", "not_attempted"]) {
      expect(tlsOutcomeLabel(outcome).text.toLowerCase()).not.toMatch(/probability|likely planet/);
    }
  });
});

describe("parseEventLine", () => {
  it("parses SSE data lines and skips blanks", () => {
    expect(parseEventLine("")).toBeNull();
    expect(parseEventLine('data: {"type":"done"}')).toEqual({ type: "done" });
  });

  it("rejects protocol violations instead of dropping them", () => {
    expect(() => parseEventLine("not-an-event")).toThrow();
  });
});

describe("parseLightCurveCsv", () => {
  it("parses comma-separated time,flux with comments and headers skipped", () => {
    const csv = `# demo curve\ntime,flux\n1.0,1.001\n2.0,0.999\n` + "3.0,1.0\n".repeat(10);
    const ds = parseLightCurveCsv(csv, "demo");
    expect(ds.time.length).toBeGreaterThanOrEqual(10);
    expect(ds.flux).toHaveLength(ds.time.length);
    expect(ds.target_name).toBe("demo");
  });

  it("rejects curves too short for the API minimum", () => {
    expect(() => parseLightCurveCsv("1.0,1.0\n2.0,1.0\n", "tiny")).toThrow(/at least 10/);
  });
});

describe("artifact series", () => {
  function jsonResponse(body: unknown, etag?: string) {
    return {
      ok: true,
      status: 200,
      headers: { get: (k: string) => (k.toLowerCase() === "etag" ? (etag ?? null) : null) },
      json: async () => body,
      text: async () => JSON.stringify(body),
    };
  }

  it("lists artifacts and builds decimated dataset URLs", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      calls.push(url);
      return jsonResponse({ job_id: "j1", dataset: {}, candidates: [] });
    });
    try {
      await listArtifacts("tok", "j1");
      await getDataset("tok", "j1", { max_points: 500, t_min: 1, t_max: 9 });
      await getFolded("tok", "j1", "c2", 60);
    } finally {
      vi.unstubAllGlobals();
    }
    expect(calls[0]).toMatch(/\/jobs\/j1\/artifacts$/);
    expect(calls[1]).toMatch(/type=dataset/);
    expect(calls[1]).toMatch(/max_points=500/);
    expect(calls[1]).toMatch(/t_min=1/);
    expect(calls[2]).toMatch(/type=folded&candidate=c2&bins=60/);
  });

  it("serves repeat views from the 304 cache without re-parsing", async () => {
    const payload = { job_id: "j1", n_returned: 10 };
    let hits = 0;
    vi.stubGlobal("fetch", async (_url: string, init?: { headers?: Record<string, string> }) => {
      hits += 1;
      if (init?.headers?.["if-none-match"] === '"abc"') {
        return { ok: false, status: 304, headers: { get: () => null }, text: async () => "" };
      }
      return jsonResponse(payload, '"abc"');
    });
    try {
      const first = await getDataset("tok", "j1");
      const second = await getDataset("tok", "j1");
      expect(first).toEqual(payload);
      expect(second).toEqual(payload);
      expect(hits).toBe(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("streamJobEvents", () => {
  function mockStream(chunks: string[]) {
    const queue = chunks.map((c) => new TextEncoder().encode(c));
    return {
      ok: true,
      body: {
        getReader() {
          return {
            async read() {
              const value = queue.shift();
              return value ? { done: false, value } : { done: true, value: undefined };
            },
          };
        },
      },
      text: async () => "",
    };
  }

  it("sends the bearer token and emits parsed worker events", async () => {
    const seen: unknown[] = [];
    const calls: Array<[string, RequestInit]> = [];
    vi.stubGlobal(
      "fetch",
      async (...args: [string, RequestInit]) => {
        calls.push(args);
        return mockStream(['data: {"type":"stage","stage":"SEARCHING"}\n\n']) as unknown as Response;
      },
    );
    try {
      await streamJobEvents("tok-123", "job-1", (ev) => seen.push(ev));
    } finally {
      vi.unstubAllGlobals();
    }
    expect(calls).toHaveLength(1);
    const [url, init] = calls[0];
    expect(url).toMatch(/\/jobs\/job-1\/events$/);
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer tok-123");
    expect(seen).toEqual([{ type: "stage", stage: "SEARCHING" }]);
  });

  it("throws on non-OK responses so polling takes over", async () => {
    vi.stubGlobal("fetch", async () => ({ ok: false, status: 401, text: async () => "unauthorized" }));
    try {
      await expect(streamJobEvents("bad", "job-1", () => {})).rejects.toThrow(/401/);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
