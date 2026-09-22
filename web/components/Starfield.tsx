"use client";

/**
 * Decorative starfield (P3 refresh). Pixels, not data: a quiet canvas
 * behind the landing hero. Static under prefers-reduced-motion.
 * DPR-aware, single RAF loop, cleaned up on unmount.
 */
import { useEffect, useRef } from "react";

const STARS = 140;

export default function Starfield() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let raf = 0;
    let w = 0;
    let h = 0;

    const stars = Array.from({ length: STARS }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: 0.4 + Math.random() * 1.1,
      p: Math.random() * Math.PI * 2,
      s: 0.4 + Math.random() * 0.9,
    }));

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas!.width = Math.max(1, Math.floor(w * dpr));
      canvas!.height = Math.max(1, Math.floor(h * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function draw(t: number) {
      ctx!.clearRect(0, 0, w, h);
      for (const s of stars) {
        const tw = reduced ? 0.75 : 0.45 + 0.35 * Math.sin(t / 1000 * s.s + s.p);
        ctx!.globalAlpha = Math.max(0.08, Math.min(0.85, tw));
        ctx!.fillStyle = "#bcd2f5";
        ctx!.beginPath();
        ctx!.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2);
        ctx!.fill();
      }
      ctx!.globalAlpha = 1;
      if (!reduced) raf = requestAnimationFrame(draw);
    }

    resize();
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className="starfield" />;
}
