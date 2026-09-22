"use client";

/**
 * P3-E Settings route: connection, keys, and honest scoping.
 * - API key: memory only (inherited session rule).
 * - Copilot BYOK: provider + key are *reserved* for the P3-G copilot.
 *   Saved only on explicit opt-in to localStorage, and this slice sends
 *   them nowhere — the page states that outright.
 */
import { useEffect, useState } from "react";
import { API_URL } from "../../lib/api";
import { ConnectBox, SessionProvider, useSession } from "../../lib/session";

const PROVIDERS = ["none", "google", "openai", "anthropic", "ollama"] as const;

function SettingsInner() {
  const { token } = useSession();
  const [provider, setProvider] = useState<string>("none");
  const [copilotKey, setCopilotKey] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("astraeus-byok");
      if (raw) {
        const parsed = JSON.parse(raw) as { provider?: string };
        if (parsed.provider) setProvider(parsed.provider);
        setSaved(true);
      }
    } catch {
      /* no stored keys — the default state */
    }
  }, []);

  function saveByok() {
    try {
      if (provider === "none" || !copilotKey) {
        localStorage.removeItem("astraeus-byok");
      } else {
        localStorage.setItem("astraeus-byok", JSON.stringify({ provider, key: copilotKey }));
      }
      setSaved(true);
      setCopilotKey("");
    } catch {
      setSaved(false);
    }
  }

  function clearByok() {
    try {
      localStorage.removeItem("astraeus-byok");
    } catch {
      /* already clear */
    }
    setProvider("none");
    setCopilotKey("");
    setSaved(false);
  }

  return (
    <main>
      <h1>Settings</h1>
      <p className="subtitle">Connection, keys, and what is stored where.</p>
      <section className="panel">
        <h2>API connection</h2>
        <p>
          Endpoint: <span className="mono">{API_URL}</span>
          <span className="muted"> (build-time `NEXT_PUBLIC_ASTRAEUS_API_URL`)</span>
        </p>
        <p className="muted">Status: {token ? "connected (token in memory)" : "not connected"}</p>
        <ConnectBox />
      </section>
      <section className="panel">
        <h2>Copilot keys (BYOK, reserved)</h2>
        <p className="muted">
          Reserved for the P3-G copilot. This slice sends these keys <em>nowhere</em> — no
          request leaves the browser carrying them.
        </p>
        <div className="row">
          <div>
            <label htmlFor="provider">Provider</label>
            <select id="provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="byok">Key (stored only on explicit save)</label>
            <input
              id="byok"
              type="password"
              value={copilotKey}
              onChange={(e) => setCopilotKey(e.target.value)}
              disabled={provider === "none"}
            />
          </div>
        </div>
        <div className="row">
          <div style={{ flexGrow: 0 }}>
            <button onClick={saveByok} disabled={provider === "none" && !copilotKey && !saved}>
              Save locally
            </button>
          </div>
          <div style={{ flexGrow: 0 }}>
            <button className="danger" onClick={clearByok}>
              Forget keys
            </button>
          </div>
        </div>
        {saved && <p className="muted">A provider choice is stored in this browser only.</p>}
      </section>
    </main>
  );
}

export default function SettingsPage() {
  return (
    <SessionProvider>
      <SettingsInner />
    </SessionProvider>
  );
}
