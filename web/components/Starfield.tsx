"use client";

/**
 * Observatory starfield: three depth layers (deep / mid / bright) with
 * pointer drift + scroll parallax, drawn in one kick-based RAF pass.
 *
 * Pixels, not data — purely decorative. Static first frame under
 * prefers-reduced-motion; pauses when hidden. DPR capped at 2, zero
 * per-frame allocations (precomputed star table, reused loop locals).
 */
import { useEffect, useRef } from "react";

interface Star {
  x: number;
  y: number;
  r: number;
  p: number;
  s: number;
  depth: number;
}

function buildLayer(n: number, rMin: number, rMax: number, depth: number): Star[] {
  const out: Star[] = [];
  for (let i = 0; i < n; i++) {
    out.push({
      x: Math.random(),
      y: Math.random(),
      r: rMin + Math.random() * (rMax - rMin),
      p: Math.random() * Math.PI * 2,
      s: 0.3 + Math.random() * 0.9,
      depth,
    });
  }
  return out;
}

export default function Starfield({ density = 1 }: { density?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const deep = buildLayer(Math.floor(90 * density), 0.3, 0.8, 0.25);
    const mid = buildLayer(Math.floor(42 * density), 0.5, 1.2, 0.55);
    const bright = buildLayer(Math.floor(16 * density), 0.8, 1.7, 1);
    let raf = 0;
    let w = 0;
    let h = 0;
    let px = 0;
    let py = 0;
    let tx = 0;
    let ty = 0;
    let scroll = 0;
    let dirty = true;

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      w = Math.max(1, rect.width);
      h = Math.max(1, rect.height);
      canvas!.width = Math.floor(w * dpr);
      canvas!.height = Math.floor(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      dirty = true;
      kick();
    }

    function onPointer(e: PointerEvent) {
      const rect = canvas!.getBoundingClientRect();
      tx = ((e.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * 2;
      ty = ((e.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * 2;
      dirty = true;
      kick();
    }

    function onScroll() {
      scroll = window.scrollY || 0;
      dirty = true;
      kick();
    }

    function kick() {
      if (raf || reduced) {
        if (reduced) draw(0);
        return;
      }
      raf = requestAnimationFrame(tick);
    }

    function layer(stars: Star[], t: number, driftX: number, driftY: number) {
      for (let i = 0; i < stars.length; i++) {
        const s = stars[i];
        const tw = reduced ? 0.7 : 0.42 + 0.34 * Math.sin((t / 1000) * s.s + s.p);
        const a = tw < 0.08 ? 0.08 : tw > 0.85 ? 0.85 : tw;
        ctx!.globalAlpha = a;
        ctx!.fillStyle = s.depth >= 1 ? "#d8e6ff" : "#a9c0e8";
        const x = (s.x * w + driftX * s.depth * 14 + w) % w;
        const y = (s.y * h + driftY * s.depth * 10 + scroll * 0.02 * s.depth + h) % h;
        ctx!.beginPath();
        ctx!.arc(x, y, s.r, 0, 6.2832);
        ctx!.fill();
        if (s.depth >= 1 && !reduced) {
          ctx!.globalAlpha = a * 0.18;
          ctx!.beginPath();
          ctx!.arc(x, y, s.r * 3.2, 0, 6.2832);
          ctx!.fill();
        }
      }
    }

    function draw(t: number) {
      ctx!.clearRect(0, 0, w, h);
      layer(deep, t, px, py);
      layer(mid, t, px, py);
      layer(bright, t, px, py);
      ctx!.globalAlpha = 1;
    }

    function tick(t: number) {
      raf = 0;
      px += (tx - px) * 0.06;
      py += (ty - py) * 0.06;
      const moving = Math.abs(tx - px) > 0.001 || Math.abs(ty - py) > 0.001 || dirty;
      draw(t);
      dirty = false;
      if (!reduced && (moving || true)) {
        // Twinkle keeps one layer alive; pause entirely when hidden.
        if (!document.hidden) raf = requestAnimationFrame(tick);
      }
    }

    function onVisibility() {
      if (!document.hidden && !reduced && !raf) raf = requestAnimationFrame(tick);
    }

    resize();
    draw(0);
    if (!reduced) raf = requestAnimationFrame(tick);
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      raf = 0;
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("scroll", onScroll);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [density]);

  return <canvas ref={ref} aria-hidden className="starfield" />;
}
