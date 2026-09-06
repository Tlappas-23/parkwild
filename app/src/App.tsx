import { lazy, Suspense, useEffect } from "react";
import { hardReload, stripFreshParam } from "./data";
import { PARKS, useStore } from "./store";
import SpeciesPage from "./pages/SpeciesPage";
import AboutPage from "./pages/AboutPage";

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

export default function App() {
  const { page, setPage, load, error, species, park, parkName, setPark } = useStore();
  useEffect(() => { stripFreshParam(); nudgeWaitingWorker(); void load(); }, [load]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-row">
          <button className="brand" onClick={() => setPage("map")} aria-label="parkwild home">
            <svg width="26" height="26" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="16" fill="currentColor" opacity="0.12" /><path d="M32 12 L49 22 L49 42 L32 52 L15 42 L15 22 Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" /><circle cx="32" cy="32" r="5" fill="currentColor" /></svg>
            <span>parkwild</span>
          </button>
          {/* The park list is whatever this build has data for; one select, no routing. */}
          {PARKS.length > 1 ? (
            <select className="park-select" aria-label="Park" value={park} onChange={(e) => setPark(e.target.value)}>
              {PARKS.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
            </select>
          ) : (
            <span className="park">{parkName}</span>
          )}
        </div>
        <nav aria-label="Pages">
          {(["map", "species", "about"] as const).map((p) => (
            <button key={p} className={page === p ? "active" : ""} aria-current={page === p ? "page" : undefined} onClick={() => setPage(p)}>
              {p === "map" ? "Map" : p === "species" ? "Species" : "About"}
            </button>
          ))}
        </nav>
      </header>
      <main className={page === "map" ? "main-map" : ""}>
        {error && (
          <div role="alert" className="error">
            Data could not be loaded: {error}{" "}
            <button className="ghost" onClick={() => void hardReload()}>Reload</button>
          </div>
        )}
        {!error && !species && <div className="loading"><div className="spinner" aria-hidden="true" /><p className="muted">Loading {parkName}…</p></div>}
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
