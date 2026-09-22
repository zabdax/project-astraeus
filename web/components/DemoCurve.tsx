"use client";

/**
 * Hero visual: the real Kepler-90 demo curve (cached, downsampled).
 * Fetched as JSON, drawn with uPlot. The caption states exactly what
 * it is — a rendering, not analysis output.
 */
import { useEffect, useState } from "react";
import LightCurve from "./LightCurve";

interface DemoCurve {
  target: string;
  mission: string;
  n_cadences: number;
  baseline_days: number;
  time_bjd: number[];
  flux: number[];
  note: string;
}

export default function DemoCurve() {
  const [curve, setCurve] = useState<DemoCurve | null>(null);

  useEffect(() => {
    fetch("/demo-curve.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setCurve)
      .catch(() => setCurve(null));
  }, []);

  if (!curve) return <div className="skeleton" style={{ height: 260 }} aria-label="loading demo curve" />;

  return (
    <figure style={{ margin: 0 }}>
      <LightCurve
        x={curve.time_bjd}
        y={curve.flux}
        title={`${curve.target} · ${curve.mission}`}
        xlabel="BJD"
        height={240}
      />
      <figcaption className="muted" style={{ fontSize: 12, marginTop: 6 }}>
        {curve.n_cadences.toLocaleString()} cadences · {curve.baseline_days.toLocaleString()} d baseline ·{" "}
        {curve.note}
      </figcaption>
    </figure>
  );
}
