"use client";

/**
 * Orbit visual for the Simulate workbench: top-down path + edge-on
 * chord against the stellar disc, drawn from the same elements as the
 * KPIs. Decorative planet dot animates unless reduced-motion is set.
 */
import { useEffect, useRef } from "react";
import { sampleOrbit, type OrbitElements } from "../lib/orbit";

export default function OrbitView({ elements }: { elements: OrbitElements }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const elRef = useRef(elements);
  elRef.current = elements;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let raf = 0;

    function draw(t: number) {
      const el = elRef.current;
      const rect = canvas!.getBoundingClientRect();
      const W = rect.width;
      const H = 190;
      if (canvas!.width !== Math.floor(W * dpr)) {
        canvas!.width = Math.floor(W * dpr);
        canvas!.height = Math.floor(H * dpr);
      }
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx!.clearRect(0, 0, W, H);

      const pts = sampleOrbit(el, 220);
      const half = W / 4 - 14;
      const cx1 = W / 4;
      const cx2 = (3 * W) / 4;
      const cy = H / 2 + 8;

      const maxR = Math.max(...pts.map((p) => Math.hypot(p.x_au, p.y_au)), 1e-9);
      const s = half / maxR;

      // --- top-down ---
      ctx!.strokeStyle = "#33436a";
      ctx!.lineWidth = 1.5;
      ctx!.beginPath();
      pts.forEach((p, i) => {
        const x = cx1 + p.x_au * s;
        const y = cy - p.y_au * s;
        if (i === 0) ctx!.moveTo(x, y);
        else ctx!.lineTo(x, y);
      });
      ctx!.closePath();
      ctx!.stroke();
      // star
      ctx!.fillStyle = "#e8c46a";
      ctx!.beginPath();
      ctx!.arc(cx1, cy, 5, 0, Math.PI * 2);
      ctx!.fill();
      ctx!.fillStyle = "#8f9bb3";
      ctx!.font = "11px 'IBM Plex Mono', monospace";
      ctx!.fillText("top-down", cx1 - 30, H - 4);

      // --- edge-on: stellar disc + transit chord ---
      const rPx = 34;
      const grad = ctx!.createRadialGradient(cx2, cy, 4, cx2, cy, rPx);
      grad.addColorStop(0, "#f4d98c");
      grad.addColorStop(1, "#8a6a35");
      ctx!.fillStyle = grad;
      ctx!.beginPath();
      ctx!.arc(cx2, cy, rPx, 0, Math.PI * 2);
      ctx!.fill();
      const chord = pts.map((p) => ({ x: cx2 + p.sky_x * rPx, z: cy - p.sky_z * rPx }));
      ctx!.strokeStyle = "#6cb0ff";
      ctx!.lineWidth = 1.5;
      ctx!.beginPath();
      chord.forEach((p, i) => {
        if (i === 0) ctx!.moveTo(p.x, p.z);
        else ctx!.lineTo(p.x, p.z);
      });
      ctx!.stroke();
      ctx!.fillStyle = "#8f9bb3";
      ctx!.fillText("edge-on", cx2 - 26, H - 4);

      // planet dot (phase-advanced with wall time for display only)
      if (!reduced) {
        const k = (t / 6000) % 1;
        const p = pts[Math.floor(k * pts.length)];
        ctx!.fillStyle = "#6cb0ff";
        ctx!.beginPath();
        ctx!.arc(cx1 + p.x_au * s, cy - p.y_au * s, 3, 0, Math.PI * 2);
        ctx!.fill();
        raf = requestAnimationFrame(draw);
      }
    }

    const resize = () => draw(performance.now());
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} aria-label="Orbit diagram" style={{ width: "100%", height: 190, display: "block" }} />;
}
