import { useEffect, useMemo, useRef } from "react";
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { filteredFeatures, useStore } from "../store";
import CellDetail from "./CellDetail";

// OSM raster tiles: free, attribution required (shown by the control). Traffic
// stays within OSM's tile usage policy for a small app; Protomaps is the
// documented alternative if that ever changes.
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const YELLOWSTONE_CENTER: [number, number] = [-110.5, 44.6];

export default function MapPage() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const { cells, species, speciesFilter, yearRange, setSpeciesFilter, setYearRange, selectCell, reducedMotion } = useStore();

  const features = useMemo(() => filteredFeatures(cells, speciesFilter, yearRange), [cells, speciesFilter, yearRange]);
  const years = useMemo(() => {
    let lo = 2100, hi = 1900;
    for (const f of cells?.features ?? []) {
      if (f.properties.y0 !== null) lo = Math.min(lo, f.properties.y0);
      if (f.properties.y1 !== null) hi = Math.max(hi, f.properties.y1);
    }
    return lo <= hi ? [lo, hi] : [1900, 2100];
  }, [cells]);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: YELLOWSTONE_CENTER,
      zoom: 8,
      attributionControl: { compact: false },
      fadeDuration: reducedMotion ? 0 : 300,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("cells", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      // Soft, low-opacity fills on purpose: a cell is a probability, not a point.
      map.addLayer({
        id: "cells-fill",
        type: "fill",
        source: "cells",
        paint: {
          "fill-color": ["case", [">", ["get", "mp"], 0], "#b86e00", "#2a78d6"],
          // Opacity on a log scale: 1 sighting is faint, 1000 is solid-ish, and
          // the jump from 1 to 10 reads the same as 10 to 100.
          "fill-opacity": ["interpolate", ["linear"], ["log10", ["max", 1, ["get", "count"]]], 0, 0.12, 1, 0.3, 2, 0.5, 3, 0.65],
          "fill-outline-color": "rgba(255,255,255,0.35)",
        },
      });
      map.on("click", "cells-fill", (e) => {
        const f = e.features?.[0];
        if (f) selectCell(String(f.properties.cell));
      });
      map.on("mouseenter", "cells-fill", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "cells-fill", () => (map.getCanvas().style.cursor = ""));
      mapRef.current = map;
      // Push whatever is already filtered.
      (map.getSource("cells") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features });
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const src = map?.getSource("cells") as maplibregl.GeoJSONSource | undefined;
    src?.setData({ type: "FeatureCollection", features });
  }, [features]);

  const options = species?.species.filter((s) => s.suppression?.action !== "exclude") ?? [];

  return (
    <div className="map-page">
      <div className="filters" role="group" aria-label="Filters">
        <label>
          Species
          <select value={speciesFilter ?? ""} onChange={(e) => setSpeciesFilter(e.target.value || null)}>
            <option value="">All species</option>
            {options.map((s) => (
              <option key={s.scientific_name} value={s.scientific_name}>
                {s.common_name ?? s.scientific_name} ({s.sightings.toLocaleString()})
              </option>
            ))}
          </select>
        </label>
        <label>
          From {yearRange[0]}
          <input type="range" min={years[0]} max={years[1]} value={yearRange[0]} aria-label="Start year"
            onChange={(e) => setYearRange([Math.min(+e.target.value, yearRange[1]), yearRange[1]])} />
        </label>
        <label>
          To {yearRange[1]}
          <input type="range" min={years[0]} max={years[1]} value={yearRange[1]} aria-label="End year"
            onChange={(e) => setYearRange([yearRange[0], Math.max(+e.target.value, yearRange[0])])} />
        </label>
        <span className="muted small">{features.length.toLocaleString()} cells shown</span>
      </div>
      <div className="map-wrap">
        <div ref={container} className="map" role="region" aria-label="Map of aggregated sightings" />
        <CellDetail />
      </div>
      <p className="muted small legend">
        <span className="swatch human" /> human-verified &nbsp; <span className="swatch model" /> includes model-predicted &nbsp;
        Cells are ~170 m hexagons (larger for sensitive species). An empty cell means nobody looked, not that nothing lives there.
      </p>
    </div>
  );
}
