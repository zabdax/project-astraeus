"use client";

/**
 * Count-up readout for measured numbers. Animates the numeric prefix
 * once on first view (IntersectionObserver), ease-out-expo over 900ms,
 * tabular figures so columns never shift. Static text under
 * prefers-reduced-motion. Non-numeric entries render as-is.
 */
import { useEffect, useRef, useState } from "react";

interface Props {
  value: number | null;
  decimals?: number;
  suffix?: string;
  display: string;
}

export default function CountUp({ value, decimals = 0, suffix = "", display }: Props) {
  const ref = useRef<HTMLElement>(null);
  const [text, setText] = useState(display);
  const done = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || value === null || done.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting || done.current) continue;
          done.current = true;
          const t0 = performance.now();
          const dur = 900;
          function frame(t: number) {
            const k = Math.min(1, (t - t0) / dur);
            const e = 1 - Math.pow(1 - k, 4);
            setText(`${(value! * e).toFixed(decimals)}${suffix}`);
            if (k < 1) requestAnimationFrame(frame);
            else setText(display);
          }
          requestAnimationFrame(frame);
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [value, decimals, suffix, display]);

  return <dt ref={ref}>{text}</dt>;
}
