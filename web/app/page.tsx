"use client";

/**
 * Landing (Explore demoted per PRD §9): the user's own recent work lives
 * in Analyses; this view shows API liveness and route links — honest by
 * construction, never synthesized figures.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { API_URL } from "../lib/api";

export default function Home() {
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((b) => setHealth(`ok · v${b.version} · single-user: ${String(b.single_user)}`))
      .catch(() => setHealth("unreachable — start the API (`py -m astraeus.api.main`)"));
  }, []);

  return (
    <main>
      <h1>ASTRAEUS</h1>
      <p className="subtitle">Autonomous Scientific Tool for Research and Analysis of Space</p>
      <section className="panel">
        <h2>API</h2>
        <p className="mono">{health}</p>
      </section>
      <section className="panel">
        <h2>Routes</h2>
        <div className="row">
          <Link href="/investigate">Investigate — run a search on real data</Link>
          <Link href="/analyses">Analyses — jobs, results, provenance, exports</Link>
          <Link href="/simulate">Simulate — synthetic sandbox (labelled)</Link>
          <Link href="/settings">Settings — connection, keys, display</Link>
        </div>
      </section>
    </main>
  );
}
