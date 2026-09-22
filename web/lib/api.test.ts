/**
 * P2-B client tests: the UI must never lie about the API contract.
 * Field paths asserted here mirror the P2-A slice result shape
 * (`AnalysisResult.to_dict` + `TlsSummary` + per-candidate `TlsEvidence`).
 */
import { describe, expect, it } from "vitest";
import { parseEventLine, parseLightCurveCsv, tlsOutcomeLabel } from "./api";

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
