import { lazy, Suspense, useEffect } from "react";
import { useStore } from "./store";
import SpeciesPage from "./pages/SpeciesPage";
import AboutPage from "./pages/AboutPage";

// The map page pulls in maplibre-gl (its own chunk); it is loaded only when shown.
const MapPage = lazy(() => import("./pages/MapPage"));

export default function App() {
  const { page, setPage, load, error, species } = useStore();
  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand" onClick={() => setPage("map")}>parkwild</h1>
        <nav aria-label="Pages">
          {(["map", "species", "about"] as const).map((p) => (
            <button key={p} className={page === p ? "active" : ""} aria-current={page === p ? "page" : undefined} onClick={() => setPage(p)}>
              {p === "map" ? "Map" : p === "species" ? "Species" : "About"}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {error && (
          <div role="alert" className="error">
            Data could not be loaded: {error}
          </div>
        )}
        {!error && !species && <p className="muted">Loading Yellowstone…</p>}
        {species && page === "map" && (
          <Suspense fallback={<p className="muted">Loading map…</p>}>
            <MapPage />
          </Suspense>
        )}
        {species && page === "species" && <SpeciesPage />}
        {species && page === "about" && <AboutPage />}
      </main>
    </div>
  );
}
