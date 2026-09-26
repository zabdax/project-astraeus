"use client";

/**
 * Scroll reveal without a library: IntersectionObserver adds `.is-in`
 * once; CSS owns the motion (transform + opacity only). Variants keep
 * one orchestrated language: rise (default), scale (bento cards),
 * none (content that should just appear). Collapses to instant under
 * prefers-reduced-motion.
 */
import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  delay?: number;
  className?: string;
  variant?: "rise" | "scale" | "none";
}

export default function Reveal({ children, delay = 0, className = "", variant = "rise" }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.classList.add("is-in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const variantClass = variant === "none" ? "" : variant === "scale" ? "reveal-scale" : "reveal";
  return (
    <div ref={ref} className={`${variantClass} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}
