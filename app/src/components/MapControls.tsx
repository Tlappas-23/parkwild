import { useMemo, useState } from "react";
import { ChevronLeft, Globe, Play, Route, SlidersHorizontal } from "lucide-react";
import { PARKS_INDEX } from "../data/parksIndex";
import { tourStops } from "../lib/tour";
import { speciesMatches, useStore } from "../store/index";
import ParkLive from "./ParkLive";
import PlanPanel from "./PlanPanel";
import WeatherChip from "./WeatherChip";

// The left panel of the map, in three parts a visitor can read top to bottom:
// View (how the map is drawn), Now (weather and USGS readings at the park's
// busiest place; folds away), Filter (species and years). Folded, it is a
// "Filters" pill and a weather pill.
export default function MapControls({
  overview,
  setOverview,
  years,
  total,
  cellCount,
}: {
  overview: boolean;
  setOverview: (f: (v: boolean) => boolean) => void;
  years: [number, number];
  total: number;
  cellCount: number;
}) {
  const {
    park,
    species,
    landmarks,
    tour,
    startTour,
    basemap,
    setBasemap,
    terrain3d,
    setTerrain3d,
    plan,
    openPlan,
    speciesFilter,
    setSpeciesFilter,
    yearRange,
    setYearRange,
    controlsOpen,
    setControlsOpen,
    climate,
  } = useStore();
  const [query, setQuery] = useState("");
  const stops = useMemo(() => tourStops(landmarks), [landmarks]);
  const parkCard = PARKS_INDEX.parks.find((p) => p.key === park);
  const weatherAt = climate
    ? { lat: climate.lat, lon: climate.lon, at: climate.at }
    : parkCard?.center
      ? { lat: parkCard.center[1], lon: parkCard.center[0], at: undefined }
      : null;
  const options = useMemo(() => {
    const list = (species?.species ?? []).filter((s) => s.suppression?.action !== "exclude");
    const q = query.trim();
    return q ? list.filter((s) => speciesMatches(s, q)).slice(0, 12) : [];
  }, [species, query]);
  const current = species?.species.find((s) => s.scientific_name === speciesFilter);

  return (
    <>
      {!controlsOpen && (
        <button className="controls-pill" onClick={() => setControlsOpen(true)} aria-label="Show filters and tools">
          <SlidersHorizontal className="ico" aria-hidden="true" /> Filters
          {current ? <span className="pill-chip">{current.common_name ?? current.scientific_name}</span> : null}
          {plan.open ? <span className="pill-chip">route</span> : null}
        </button>
      )}
      {!controlsOpen && weatherAt && (
        <div className="weather-pill" aria-label="Weather now">
          <WeatherChip lat={weatherAt.lat} lon={weatherAt.lon} compact />
        </div>
      )}
      <div className="controls" role="group" aria-label="Filters" hidden={!controlsOpen}>
        <button
          className="icon-btn controls-hide"
          onClick={() => setControlsOpen(false)}
          aria-label="Hide filters and tools"
          title="Hide panel"
        >
          <ChevronLeft className="ico" aria-hidden="true" />
        </button>
        {stops.length > 0 && !tour.active && (
          <button className="primary tour-start" onClick={startTour}>
            <Play className="ico" aria-hidden="true" /> Take the tour
          </button>
        )}

        <section className="panel-sec" aria-label="View">
          <div className="panel-head">View</div>
          <div className="control view-row">
            <div className="seg" role="group" aria-label="Basemap">
              <button
                className={basemap === "terrain" ? "on" : ""}
                aria-pressed={basemap === "terrain"}
                onClick={() => setBasemap("terrain")}
              >
                Terrain
              </button>
              <button
                className={basemap === "satellite" ? "on" : ""}
                aria-pressed={basemap === "satellite"}
                onClick={() => setBasemap("satellite")}
              >
                Satellite
              </button>
              <button
                className={basemap === "topo" ? "on" : ""}
                aria-pressed={basemap === "topo"}
                onClick={() => setBasemap("topo")}
              >
                Topo
              </button>
            </div>
            <button
              className={"toggle" + (terrain3d ? " on" : "")}
              aria-pressed={terrain3d}
              onClick={() => setTerrain3d(!terrain3d)}
            >
              3D
            </button>
          </div>
          <div className="control view-row">
            {!plan.open && (
              <button className="toggle" onClick={openPlan}>
                <Route className="ico" aria-hidden="true" /> Plan a visit
              </button>
            )}
            <button
              className={"toggle" + (overview ? " on" : "")}
              aria-pressed={overview}
              onClick={() => setOverview((v) => !v)}
            >
              <Globe className="ico" aria-hidden="true" /> All parks
            </button>
          </div>
        </section>

        {weatherAt && (
          <details className="panel-sec now" open>
            <summary className="panel-head">Now{weatherAt.at ? ` · ${weatherAt.at}` : ""}</summary>
            <WeatherChip lat={weatherAt.lat} lon={weatherAt.lon} climate={climate} />
            {parkCard?.bbox && <ParkLive bbox={parkCard.bbox} parkName={parkCard.name} />}
          </details>
        )}

        <section className="panel-sec" aria-label="Filter">
          <div className="panel-head">Filter</div>
          <div className="control">
            <label htmlFor="species-search">Species</label>
            {current ? (
              <div className="chip-row">
                <span className="chip">
                  {current.common_name ?? current.scientific_name}
                  <button
                    className="chip-x"
                    aria-label="Clear species filter"
                    onClick={() => {
                      setSpeciesFilter(null);
                      setQuery("");
                    }}
                  >
                    ×
                  </button>
                </span>
              </div>
            ) : (
              <div className="search">
                <input
                  id="species-search"
                  type="search"
                  placeholder="Search bison, elk, raven…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoComplete="off"
                />
                {options.length > 0 && (
                  <ul className="suggest" role="listbox">
                    {options.map((s) => (
                      <li key={s.scientific_name} role="option" aria-selected="false">
                        <button
                          onClick={() => {
                            setSpeciesFilter(s.scientific_name);
                            setQuery("");
                          }}
                        >
                          <span>{s.common_name ?? s.scientific_name}</span>
                          <span className="muted small">{s.sightings.toLocaleString()}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
          <div className="control years">
            <label>
              Years{" "}
              <span className="muted">
                {yearRange[0]}–{yearRange[1]}
              </span>
            </label>
            <div className="range-pair">
              <input
                type="range"
                min={years[0]}
                max={years[1]}
                value={yearRange[0]}
                aria-label="Start year"
                onChange={(e) => setYearRange([Math.min(+e.target.value, yearRange[1]), yearRange[1]])}
              />
              <input
                type="range"
                min={years[0]}
                max={years[1]}
                value={yearRange[1]}
                aria-label="End year"
                onChange={(e) => setYearRange([yearRange[0], Math.max(+e.target.value, yearRange[0])])}
              />
            </div>
          </div>
          <p className="muted small stat">
            {total.toLocaleString()} sightings in {cellCount.toLocaleString()} cells
          </p>
        </section>
        {plan.open && <PlanPanel />}
      </div>
    </>
  );
}
