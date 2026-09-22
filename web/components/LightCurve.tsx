"use client";

/**
 * P3-F flagship light-curve chart (uPlot). Thin wrapper: data in, pixels
 * out. Destroys the chart on unmount / data change — no leaked instances.
 */
import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

interface Props {
  x: number[];
  y: number[];
  title: string;
  xlabel?: string;
  height?: number;
}

export default function LightCurve({ x, y, title, xlabel, height = 260 }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || x.length === 0) return;
    el.innerHTML = "";
    const width = Math.max(280, el.clientWidth || 640);
    const plot = new uPlot(
      {
        title,
        width,
        height,
        scales: { x: { time: false } },
        axes: [
          { label: xlabel ?? "x" },
          { label: "flux", values: (_u, v) => v.map((n) => Number(n).toFixed(4)) },
        ],
        series: [{}, { stroke: "#5aa9ff", width: 1, points: { show: false } }],
      },
      [x, y],
      el,
    );
    return () => plot.destroy();
  }, [x, y, title, xlabel, height]);

  return <div ref={ref} role="img" aria-label={title} />;
}
