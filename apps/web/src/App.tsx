import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { AUTH_REQUIRED_EVENT, ApiError, getSession, login, logout } from "./lib/api";
import { ConvertPage } from "./pages/ConvertPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "locked">("checking");
  const [accessToken, setAccessToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;

    getSession()
      .then((session) => {
        if (!mounted) {
          return;
        }
        setAuthState(session.authenticated ? "authenticated" : "locked");
      })
      .catch((err: Error) => {
        if (!mounted) {
          return;
        }
        setError(err.message);
        setAuthState("locked");
      });

    function handleAuthRequired() {
      setAuthState("locked");
      setError("Your session expired. Enter the access token again.");
    }

    window.addEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
    return () => {
      mounted = false;
      window.removeEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
    };
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(accessToken);
      setAccessToken("");
      setAuthState("authenticated");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unable to sign in.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    await logout();
    setAuthState("locked");
    setError("");
  }

  if (authState !== "authenticated") {
    return (
      <div className="app-shell auth-shell">
        <section className="card stack auth-card">
          <div>
            <p className="eyebrow">Protected Access</p>
            <h1>NAC TTS</h1>
          </div>
          <p className="muted">
            Enter the shared access token configured on the server. Browser sessions stay active until you sign out or the
            session expires.
          </p>
          <form className="stack" onSubmit={handleLogin}>
            <label className="field">
              <span>Access Token</span>
              <input
                type="password"
                value={accessToken}
                onChange={(event) => setAccessToken(event.target.value)}
                placeholder="Paste the deployment token"
                autoComplete="current-password"
              />
            </label>
            {error ? <p className="error-banner">{error}</p> : null}
            <button type="submit" className="primary-button" disabled={busy || authState === "checking"}>
              {busy || authState === "checking" ? "Checking..." : "Unlock App"}
            </button>
          </form>
        </section>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Local GPU Narration</p>
          <h1>NAC TTS</h1>
        </div>
        <div className="header-actions">
          <nav className="top-nav">
            <NavLink to="/">Convert</NavLink>
            <NavLink to="/library">Library</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
          <button type="button" className="ghost-button" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </header>
      <main className="page-frame">
        <Routes>
          <Route path="/" element={<ConvertPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
