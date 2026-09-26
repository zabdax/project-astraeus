"use client";

/**
 * Interactive 3D orbit console.
 *
 * Real Kepler geometry (solves Kepler's equation per sample, applies
 * inclination) projected through a draggable camera (azimuth/elevation
 * + perspective zoom). The planet dot plays along the orbit; when it
 * crosses the stellar disc the transit marker fires and the depth bar
 * reads the configured depth fraction. Display-only phase — science
 * still comes from the API, never from this canvas.
 *
 * Pointer: drag to rotate · wheel to zoom · Space to play/pause ·
 * arrows to nudge the camera. Static frame under reduced-motion.
 */
import { useEffect, useRef, useState } from "react";
import { sampleOrbit, type OrbitElements } from "../lib/orbit";

interface Props {
  elements: OrbitElements;
  depthFraction?: number;
  autoPlay?: boolean;
}

const N = 256;

export default function OrbitView({ elements, depthFraction = 0.01, autoPlay = true }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const elRef = useRef(elements);
  elRef.current = elements;
  const depthRef = useRef(depthFraction);
  depthRef.current = depthFraction;
  const [playing, setPlaying] = useState(autoPlay);
  const playRef = useRef(playing);
  playRef.current = playing;
  const viewRef = useRef({ az: -0.6, el: 0.42, zoom: 1 });
  const kickRef = useRef<(() => void) | null>(null);
  const [transit, setTransit] = useState(false);
  const transitRef = useRef(false);
  const [hint, setHint] = useState(true);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let raf = 0;
    let phase = 0.15;
    let last = performance.now();
    let dragging = false;
    let dragMoved = false;
    let lx = 0;
    let ly = 0;

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      const w = Math.max(280, rect.width);
      const h = 340;
      canvas!.width = Math.floor(w * dpr);
      canvas!.height = Math.floor(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function project(x: number, y: number, z: number, cx: number, cy: number, s: number) {
      const v = viewRef.current;
      const cosAz = Math.cos(v.az);
      const sinAz = Math.sin(v.az);
      const cosEl = Math.cos(v.el);
      const sinEl = Math.sin(v.el);
      const x1 = x * cosAz - y * sinAz;
      const y1 = x * sinAz + y * cosAz;
      const y2 = y1 * cosEl - z * sinEl;
      const z2 = y1 * sinEl + z * cosEl;
      const persp = 1 / (1 + z2 * 0.28 * v.zoom);
      return { sx: cx + x1 * s * persp, sy: cy - y2 * s * persp, depth: persp, z: z2 };
    }

    function draw(now: number) {
      const el = elRef.current;
      const rect = canvas!.getBoundingClientRect();
      const W = Math.max(280, rect.width);
      const H = 340;
      ctx!.clearRect(0, 0, W, H);
      const pts = sampleOrbit(el, N);
      let maxR = 1e-9;
      for (let i = 0; i < pts.length; i++) {
        const r = Math.hypot(pts[i].x_au, pts[i].y_au);
        if (r > maxR) maxR = r;
      }
      const v = viewRef.current;
      const base = Math.min(W, H * 1.35) / 2 - 26;
      const s = (base / maxR) * v.zoom;
      const cx = W / 2;
      const cy = H / 2 + 6;

      // Orbit path (3D projected, depth-faded).
      for (let i = 0; i <= pts.length; i++) {
        const p = pts[i % pts.length];
        const pr = project(p.x_au, p.y_au, 0, cx, cy, s);
        const alpha = 0.25 + 0.55 * Math.min(1.3, Math.max(0.4, pr.depth));
        ctx!.strokeStyle = `rgba(108,176,255,${alpha.toFixed(3)})`;
        ctx!.lineWidth = pr.depth > 1 ? 2 : 1.2;
        if (i === 0) ctx!.beginPath();
        else ctx!.lineTo(pr.sx, pr.sy);
      }
      ctx!.closePath();
      ctx!.stroke();

      // Star with limb-darkened disc (quadratic approx: bright core, dark limb).
      const rPx = Math.max(10, 30 * v.zoom);
      const g = ctx!.createRadialGradient(cx, cy, rPx * 0.05, cx, cy, rPx);
      g.addColorStop(0, "#fff3d0");
      g.addColorStop(0.55, "#f0cd7e");
      g.addColorStop(0.85, "#a67c3a");
      g.addColorStop(1, "#5e441f");
      ctx!.fillStyle = g;
      ctx!.beginPath();
      ctx!.arc(cx, cy, rPx, 0, 6.2832);
      ctx!.fill();
      ctx!.strokeStyle = "rgba(232,196,106,.35)";
      ctx!.lineWidth = 1;
      ctx!.stroke();

      // Planet at current phase.
      const k = ((phase % 1) + 1) % 1;
      const p = pts[Math.floor(k * pts.length) % pts.length];
      const pr = project(p.x_au, p.y_au, 0, cx, cy, s);
      const inFront = pr.z > 0;
      const distPx = Math.hypot(pr.sx - cx, pr.sy - cy);
      const isTransit = inFront && distPx < rPx;
      if (isTransit !== transitRef.current) {
        transitRef.current = isTransit;
        setTransit(isTransit);
      }
      // Glow (additive, cheap) then body.
      ctx!.globalCompositeOperation = "lighter";
      ctx!.globalAlpha = isTransit ? 0.5 : 0.28;
      ctx!.fillStyle = "#6cb0ff";
      ctx!.beginPath();
      ctx!.arc(pr.sx, pr.sy, isTransit ? 9 : 7, 0, 6.2832);
      ctx!.fill();
      ctx!.globalCompositeOperation = "source-over";
      ctx!.globalAlpha = 1;
      ctx!.fillStyle = isTransit ? "#cfe6ff" : "#6cb0ff";
      ctx!.beginPath();
      ctx!.arc(pr.sx, pr.sy, 3.4, 0, 6.2832);
      ctx!.fill();
      if (isTransit) {
        ctx!.strokeStyle = "rgba(207,230,255,.8)";
        ctx!.lineWidth = 1;
        ctx!.beginPath();
        ctx!.arc(pr.sx, pr.sy, 6, 0, 6.2832);
        ctx!.stroke();
      }

      // Readout.
      ctx!.fillStyle = "#8f9bb3";
      ctx!.font = "11px 'IBM Plex Mono', monospace";
      const azD = Math.round((v.az * 180) / Math.PI);
      const elD = Math.round((v.el * 180) / Math.PI);
      ctx!.fillText(`az ${azD}° · el ${elD}° · zoom ${v.zoom.toFixed(2)}×`, 10, H - 10);
      if (isTransit) {
        ctx!.fillStyle = "#cfe6ff";
        ctx!.fillText(`TRANSIT · depth ${(depthRef.current * 1e6).toFixed(0)} ppm`, 10, H - 26);
      }
    }

    function tick(now: number) {
      raf = 0;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (playRef.current && !reduced && !dragging) {
        phase += dt / 14;
      }
      draw(now);
      if (!reduced && (playRef.current || dragging)) raf = requestAnimationFrame(tick);
      else if (!reduced && !playRef.current && !dragging) {
        // Park the loop when paused and idle; interactions re-kick it.
      }
    }

    function kick() {
      if (!raf && !reduced) {
        last = performance.now();
        raf = requestAnimationFrame(tick);
      } else if (reduced) {
        draw(performance.now());
      }
    }
    kickRef.current = kick;

    function onDown(e: PointerEvent) {
      dragging = true;
      dragMoved = false;
      lx = e.clientX;
      ly = e.clientY;
      canvas!.setPointerCapture(e.pointerId);
      kick();
    }
    function onMove(e: PointerEvent) {
      if (!dragging) return;
      const dx = e.clientX - lx;
      const dy = e.clientY - ly;
      if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
      lx = e.clientX;
      ly = e.clientY;
      const v = viewRef.current;
      v.az += dx * 0.006;
      v.el = Math.min(1.35, Math.max(-1.35, v.el + dy * 0.004));
      draw(performance.now());
    }
    function onUp() {
      dragging = false;
      if (!playRef.current) draw(performance.now());
      else kick();
    }
    function onWheel(e: WheelEvent) {
      e.preventDefault();
      const v = viewRef.current;
      v.zoom = Math.min(2.6, Math.max(0.55, v.zoom * (e.deltaY > 0 ? 0.93 : 1.075)));
      draw(performance.now());
    }
    function onKey(e: KeyboardEvent) {
      const v = viewRef.current;
      if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "ArrowLeft") v.az -= 0.08;
      else if (e.key === "ArrowRight") v.az += 0.08;
      else if (e.key === "ArrowUp") v.el = Math.min(1.35, v.el + 0.06);
      else if (e.key === "ArrowDown") v.el = Math.max(-1.35, v.el - 0.06);
      else return;
      draw(performance.now());
      if (playRef.current) kick();
    }

    resize();
    draw(performance.now());
    if (!reduced && playRef.current) raf = requestAnimationFrame(tick);
    window.addEventListener("resize", resize);
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onUp);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-kick the loop when play state changes; redraw static frame when paused.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    kickRef.current?.();
  }, [playing]);

  const label =
    `3D orbit: period ${elements.period_days} days, eccentricity ${elements.eccentricity}, ` +
    `inclination ${elements.inclination_deg} degrees. Drag to rotate, scroll to zoom.`;

  return (
    <div ref={wrapRef} className="orbit-console">
      <div className="orbit-toolbar">
        <button
          className={playing ? "secondary" : ""}
          onClick={() => {
            setPlaying((p) => !p);
            setHint(false);
          }}
          aria-pressed={playing}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <span className={`orbit-flag ${transit ? "on" : ""}`} role="status">
          <span className="status-dot" />
          {transit ? "transit — planet on disc" : "out of transit"}
        </span>
        {hint && <span className="muted orbit-hint">drag to rotate · scroll to zoom · space to pause</span>}
      </div>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={label}
        tabIndex={0}
        className="orbit-canvas"
        onFocus={() => setHint(false)}
      />
    </div>
  );
}
