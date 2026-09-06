import { lazy, Suspense, useEffect, useState } from "react";
import { hardReload, stripFreshParam } from "./data";
import { useStore } from "./store";
import SpeciesPage from "./pages/SpeciesPage";
import AboutPage from "./pages/AboutPage";
import HomePage from "./pages/HomePage";

// The map page pulls in maplibre-gl (its own chunk); it is loaded only when shown.
const MapPage = lazy(() => import("./pages/MapPage"));

// After a deploy the new service worker installs but waits while any tab
// still runs the old one (E-027). Telling it to skip waiting means the next
// navigation gets the new shell; data URLs are content-addressed, so the
// worker changing under a running page cannot hand it the wrong file.
function nudgeWaitingWorker(): void {
  try {
    void navigator.serviceWorker?.getRegistration().then((r) => r?.waiting?.postMessage({ type: "SKIP_WAITING" }));
  } catch { /* no worker support */ }
}

// RELOAD_GRACE_MS — ARBITRARY (a controller change this soon after load is
// the update the page was waiting for, not something the visitor is doing)
const RELOAD_GRACE_MS = 30_000;

export default function App() {
  const { page, setPage, load, error, species, parkName } = useStore();
  const [updateReady, setUpdateReady] = useState(false);
  useEffect(() => { stripFreshParam(); nudgeWaitingWorker(); void load(); }, [load]);
  // When a new worker takes over: reload at once if the page just opened,
  // otherwise offer it, so a tour or a plan is never yanked away (E-034).
  useEffect(() => {
    const started = Date.now();
    let hadController = !!navigator.serviceWorker?.controller;
    const onChange = () => {
      if (!hadController) { hadController = true; return; }     // first install, nothing to swap
      if (Date.now() - started < RELOAD_GRACE_MS) window.location.reload(); else setUpdateReady(true);
    };
    try { navigator.serviceWorker?.addEventListener("controllerchange", onChange); } catch { /* no worker support */ }
    return () => { try { navigator.serviceWorker?.removeEventListener("controllerchange", onChange); } catch { /* ignore */ } };
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-row">
          <button className="brand" onClick={() => setPage("map")} aria-label="parkwild home">
            <svg width="26" height="26" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="16" fill="currentColor" opacity="0.12" /><path d="M32 12 L49 22 L49 42 L32 52 L15 42 L15 22 Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" /><circle cx="32" cy="32" r="5" fill="currentColor" /></svg>
            <span>parkwild</span>
          </button>
          {/* The current park; the home page is where parks are chosen. */}
          {page !== "home" && (
            <button className="park-link" onClick={() => setPage("home")} title="Choose another park">
              <span className="park">{parkName}</span><span className="muted small"> · change</span>
            </button>
          )}
        </div>
        <nav aria-label="Pages">
          {(["home", "map", "species", "about"] as const).map((p) => (
            <button key={p} className={page === p ? "active" : ""} aria-current={page === p ? "page" : undefined} onClick={() => setPage(p)}>
              {p === "home" ? "Parks" : p === "map" ? "Map" : p === "species" ? "Species" : "About"}
            </button>
          ))}
        </nav>
      </header>
      {updateReady && (
        <div className="update-pill" role="status">
          A newer version is ready. <button className="primary small-btn" onClick={() => window.location.reload()}>Reload</button>
        </div>
      )}
      <main className={page === "map" ? "main-map" : ""}>
        {page === "home" && <HomePage />}
        {page !== "home" && error && (
          <div role="alert" className="error">
            Data could not be loaded: {error}{" "}
            <button className="ghost" onClick={() => void hardReload()}>Reload</button>
          </div>
        )}
        {page !== "home" && !error && !species && <div className="loading"><div className="spinner" aria-hidden="true" /><p className="muted">Loading {parkName}…</p></div>}
        {species && page === "map" && (
          <Suspense fallback={<div className="loading"><div className="spinner" aria-hidden="true" /><p className="muted">Loading map…</p></div>}>
            <MapPage />
          </Suspense>
        )}
        {species && page === "species" && <SpeciesPage />}
        {species && page === "about" && <AboutPage />}
      </main>
    </div>
  );
}
