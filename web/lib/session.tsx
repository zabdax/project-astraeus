"use client";

/**
 * Shared session: API-key → bearer token, held in memory only.
 * P3-E (Settings + BYOK) owns persistence choices; until then nothing
 * here touches localStorage — a reload always re-authenticates.
 */
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { exchangeToken } from "./api";

interface Session {
  token: string | null;
  error: string | null;
  connect: (apiKey: string) => Promise<void>;
  disconnect: () => void;
}

const SessionContext = createContext<Session>({
  token: null,
  error: null,
  connect: async () => {},
  disconnect: () => {},
});

export function useSession(): Session {
  return useContext(SessionContext);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async (apiKey: string) => {
    setError(null);
    try {
      setToken(await exchangeToken(apiKey));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setToken(null);
    }
  }, []);

  const disconnect = useCallback(() => setToken(null), []);

  return (
    <SessionContext.Provider value={{ token, error, connect, disconnect }}>
      {children}
    </SessionContext.Provider>
  );
}

export function ConnectBox() {
  const { token, error, connect, disconnect } = useSession();
  const [apiKey, setApiKey] = useState("");

  if (token) {
    return (
      <p className="muted">
        Authenticated — token in memory only.{" "}
        <button className="secondary" onClick={disconnect}>
          Disconnect
        </button>
      </p>
    );
  }
  return (
    <div>
      <div className="row">
        <div>
          <label htmlFor="session-apikey">API key</label>
          <input
            id="session-apikey"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="ASTRAEUS_API_KEY value"
          />
        </div>
        <div style={{ alignSelf: "end", flexGrow: 0 }}>
          <button onClick={() => connect(apiKey)} disabled={!apiKey}>
            Connect
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
