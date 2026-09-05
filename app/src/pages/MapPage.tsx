import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { filteredFeatures, useStore } from "../store";
import CellDetail from "./CellDetail";

// Basemap: OpenFreeMap's "positron" vector style. Free, no key, no signup,
// OpenStreetMap data, muted enough that the cells are the only colour on the
// page. The first version used raw OSM raster tiles, which fought the cells.
const STYLE = "https://tiles.openfreemap.org/styles/positron";
const YELLOWSTONE_CENTER: [number, number] = [-110.55, 44.6];

export default function MapPage() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const { cells, species, speciesFilter, yearRange, setSpeciesFilter, setYearRange, selectCell, selectedCell, reducedMotion } = useStore();
  const [query, setQuery] = useState("");

  const features = useMemo(() => filteredFeatures(cells, speciesFilter, yearRange), [cells, speciesFilter, yearRange]);
  const years = useMemo(() => {
    let lo = 2100, hi = 1900;
    for (const f of cells?.features ?? []) {
      if (f.properties.y0 !== null) lo = Math.min(lo, f.properties.y0);
      if (f.properties.y1 !== null) hi = Math.max(hi, f.properties.y1);
    }
    return lo <= hi ? [lo, hi] : [1900, 2100];
  }, [cells]);
  const total = useMemo(() => features.reduce((a, f) => a + f.properties.count, 0), [features]);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current, style: STYLE, center: YELLOWSTONE_CENTER, zoom: 8.2,
      attributionControl: { compact: true }, fadeDuration: reducedMotion ? 0 : 300,
      // Keeps the last frame in the drawing buffer so screenshots and "share"
      // captures show the map instead of a blank canvas. Small GPU cost.
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    // Exposed for automated checks (queryRenderedFeatures); not part of the UI.
    (window as unknown as { __parkwildMap?: MLMap }).__parkwildMap = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => {
      map.addSource("cells", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      const color: maplibregl.ExpressionSpecification = ["case", [">", ["get", "mp"], 0], "#b86e00", "#2a78d6"];
      // Opacity on a log scale: 1 sighting is faint, 1000 is near-solid, and the
      // jump from 1 to 10 reads the same as 10 to 100.
      const opacity = (scale: number): maplibregl.ExpressionSpecification =>
        ["interpolate", ["linear"], ["log10", ["max", 1, ["get", "count"]]], 0, 0.1 * scale, 1, 0.3 * scale, 2, 0.5 * scale, 3, 0.7 * scale];
      map.addLayer({ id: "cells-coarse", type: "fill", source: "cells", filter: ["==", ["get", "coarsened"], true],
        paint: { "fill-color": color, "fill-opacity": opacity(0.45), "fill-outline-color": "rgba(42,120,214,0.3)" } });
      map.addLayer({ id: "cells-fill", type: "fill", source: "cells", filter: ["!=", ["get", "coarsened"], true],
        paint: { "fill-color": color, "fill-opacity": opacity(1), "fill-outline-color": "rgba(255,255,255,0.5)" } });
      map.addLayer({ id: "cells-selected", type: "line", source: "cells", filter: ["==", ["get", "cell"], ""],
        paint: { "line-color": "#0b0b0b", "line-width": 2 } });
      for (const layer of ["cells-fill", "cells-coarse"]) {
        map.on("click", layer, (e) => { const f = e.features?.[0]; if (f) selectCell(String(f.properties.cell)); });
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
      mapRef.current = map;
      (map.getSource("cells") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features });
    });
    // The container reaches its final size after fonts and layout settle; MapLibre
    // sized its canvas earlier. Follow the container, not the first measurement.
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);
    return () => { ro.disconnect(); map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const src = mapRef.current?.getSource("cells") as maplibregl.GeoJSONSource | undefined;
    src?.setData({ type: "FeatureCollection", features });
  }, [features]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("cells-selected")) map.setFilter("cells-selected", ["==", ["get", "cell"], selectedCell ?? ""]);
  }, [selectedCell]);

  const options = useMemo(() => {
    const list = (species?.species ?? []).filter((s) => s.suppression?.action !== "exclude");
    const q = query.trim().toLowerCase();
    return q ? list.filter((s) => (s.common_name ?? "").toLowerCase().includes(q) || s.scientific_name.toLowerCase().includes(q)).slice(0, 12) : [];
  }, [species, query]);
  const current = species?.species.find((s) => s.scientific_name === speciesFilter);

  return (
    <div className="map-page">
      <div ref={container} className="map" role="region" aria-label="Map of aggregated sightings" />

      <div className="controls" role="group" aria-label="Filters">
        <div className="control">
          <label htmlFor="species-search">Species</label>
          {current ? (
            <div className="chip-row">
              <span className="chip">{current.common_name ?? current.scientific_name}
                <button className="chip-x" aria-label="Clear species filter" onClick={() => { setSpeciesFilter(null); setQuery(""); }}>×</button>
              </span>
            </div>
          ) : (
            <div className="search">
              <input id="species-search" type="search" placeholder="Search bison, elk, raven…" value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
              {options.length > 0 && (
                <ul className="suggest" role="listbox">
                  {options.map((s) => (
                    <li key={s.scientific_name} role="option" aria-selected="false">
                      <button onClick={() => { setSpeciesFilter(s.scientific_name); setQuery(""); }}>
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
          <label>Years <span className="muted">{yearRange[0]}–{yearRange[1]}</span></label>
          <div className="range-pair">
            <input type="range" min={years[0]} max={years[1]} value={yearRange[0]} aria-label="Start year"
              onChange={(e) => setYearRange([Math.min(+e.target.value, yearRange[1]), yearRange[1]])} />
            <input type="range" min={years[0]} max={years[1]} value={yearRange[1]} aria-label="End year"
              onChange={(e) => setYearRange([yearRange[0], Math.max(+e.target.value, yearRange[0])])} />
          </div>
        </div>
        <p className="muted small stat">{total.toLocaleString()} sightings in {features.length.toLocaleString()} cells</p>
      </div>

      <div className="legend" aria-label="Legend">
        <span><i className="swatch human" /> people saw it</span>
        <span><i className="swatch model" /> includes model-predicted</span>
        <span className="muted">Cells ~170 m; larger for sensitive species. Empty means nobody looked.</span>
      </div>

      <CellDetail />
    </div>
  );
}
