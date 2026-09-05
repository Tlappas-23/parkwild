import { lazy, Suspense, useEffect } from "react";
import { useStore } from "./store";
import SpeciesPage from "./pages/SpeciesPage";
import AboutPage from "./pages/AboutPage";

// The map page pulls in maplibre-gl (its own chunk); it is loaded only when shown.
const MapPage = lazy(() => import("./pages/MapPage"));

export default function App() {
  const { page, setPage, load, error, species } = useStore();
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => setPage("map")} aria-label="parkwild home">
          <svg width="26" height="26" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="16" fill="currentColor" opacity="0.12" /><path d="M32 12 L49 22 L49 42 L32 52 L15 42 L15 22 Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" /><circle cx="32" cy="32" r="5" fill="currentColor" /></svg>
          <span>parkwild</span>
          <span className="park">Yellowstone</span>
        </button>
        <nav aria-label="Pages">
          {(["map", "species", "about"] as const).map((p) => (
            <button key={p} className={page === p ? "active" : ""} aria-current={page === p ? "page" : undefined} onClick={() => setPage(p)}>
              {p === "map" ? "Map" : p === "species" ? "Species" : "About"}
            </button>
          ))}
        </nav>
      </header>
      <main className={page === "map" ? "main-map" : ""}>
        {error && <div role="alert" className="error">Data could not be loaded: {error}</div>}
        {!error && !species && <div className="loading"><div className="spinner" aria-hidden="true" /><p className="muted">Loading Yellowstone…</p></div>}
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
