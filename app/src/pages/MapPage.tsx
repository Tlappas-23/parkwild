import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type LngLatBoundsLike, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection } from "geojson";
import { filteredFeatures, speciesMatches, useStore } from "../store";
import { STOP_PITCH, STOP_ZOOM, stopBearing, tourStops } from "../tour";
import type { BoundaryFile, LandmarksFile, Ring } from "../types";
import CellDetail from "./CellDetail";
import PlanPanel from "./PlanPanel";
import Tour from "./Tour";

// Map sources, all free and keyless (BUILD_SPEC: zero cost; never Google):
// - OpenFreeMap "liberty": OpenStreetMap roads, water, labels and fonts (ODbL)
// - USGS National Map imagery for the satellite view (public domain)
// - AWS Terrain Tiles (Terrarium PNGs built from USGS 3DEP and SRTM) for the
//   hillshade and the 3D surface; open data on S3, no credentials
// The first version was OpenFreeMap "positron" alone: flat, grey, and the
// same for every park. The park outline, relief and imagery are what make
// this look like a map of Yellowstone rather than a diagram over it.
const STYLE = "https://tiles.openfreemap.org/styles/liberty";
const USGS_IMAGERY = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}";
const TERRAIN_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
// TERRAIN_EXAGGERATION — ARBITRARY (1 is true relief; a little more reads better at a 60° pitch)
const TERRAIN_EXAGGERATION = 1.35;
// MAX_BOUNDS_PAD — ARBITRARY (how far past the boundary a visitor can pan, as a
// fraction of the park's size; this is a map of the park, not of the state)
const MAX_BOUNDS_PAD = 0.35;
const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };
const WORLD: Ring = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];

function outerRings(b: BoundaryFile | null): Ring[] {
  if (!b) return [];
  return b.geometry.type === "Polygon" ? [b.geometry.coordinates[0]] : b.geometry.coordinates.map((poly) => poly[0]);
}

function boundsOf(rings: Ring[]): [[number, number], [number, number]] | null {
  let w = 180, e = -180, s = 90, n = -90;
  for (const r of rings) for (const [x, y] of r) { w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); }
  return w <= e ? [[w, s], [e, n]] : null;
}

function padBounds(b: [[number, number], [number, number]], f: number): LngLatBoundsLike {
  const dx = (b[1][0] - b[0][0]) * f, dy = (b[1][1] - b[0][1]) * f;
  return [[b[0][0] - dx, b[0][1] - dy], [b[1][0] + dx, b[1][1] + dy]];
}

// MapLibre tells holes from outer rings by winding, so the world ring and the
// park rings must wind opposite ways for the park to be cut out of the wash.
function signedArea(r: Ring): number {
  let a = 0;
  for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
  return a;
}
function wind(r: Ring, clockwise: boolean): Ring { return (signedArea(r) < 0) === clockwise ? r : [...r].reverse(); }

function maskFC(rings: Ring[]): FeatureCollection {
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [wind(WORLD, true), ...rings.map((r) => wind(r, false))] } }] };
}
function outlineFC(rings: Ring[]): FeatureCollection {
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "MultiLineString", coordinates: rings } }] };
}
function landmarksFC(l: LandmarksFile | null): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: (l?.landmarks ?? []).map((m) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [m.lon, m.lat] },
      properties: { id: m.id, name: m.name, kind: m.kind, tour: m.tour ?? -1, stop: m.tour !== undefined, url: m.url ?? "" },
    })),
  };
}
function esc(s: string): string { return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string)); }

export default function MapPage() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const fillIds = useRef<string[]>([]);          // the style's own fill layers, hidden under imagery
  const boundsRef = useRef<[[number, number], [number, number]] | null>(null);
  const wasTouring = useRef(false);
  const [ready, setReady] = useState(false);
  const {
    cells, species, boundary, landmarks, speciesFilter, yearRange, setSpeciesFilter, setYearRange, selectCell, selectedCell,
    reducedMotion, basemap, setBasemap, terrain3d, setTerrain3d, tour, startTour, tourGo, plan, location, openPlan, addSite,
  } = useStore();
  const [query, setQuery] = useState("");
  // Handlers are registered once on the map; refs keep them pointing at the live store actions.
  const selectCellRef = useRef(selectCell); selectCellRef.current = selectCell;
  const tourGoRef = useRef(tourGo); tourGoRef.current = tourGo;
  const addSiteRef = useRef(addSite); addSiteRef.current = addSite;
  const landmarksRef = useRef(landmarks); landmarksRef.current = landmarks;

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
  const stops = useMemo(() => tourStops(landmarks), [landmarks]);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current, style: STYLE, center: [-110.5, 44.6], zoom: 7, maxPitch: 72,
      attributionControl: { compact: true }, fadeDuration: reducedMotion ? 0 : 300,
      // Keeps the last frame in the drawing buffer so screenshots and "share"
      // captures show the map instead of a blank canvas. Small GPU cost.
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    // Exposed for automated checks (queryRenderedFeatures); not part of the UI.
    (window as unknown as { __parkwildMap?: MLMap }).__parkwildMap = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), "bottom-right");
    map.on("load", () => {
      const layers = map.getStyle().layers;
      const firstLine = layers.find((l) => l.type === "line")?.id;
      const firstSymbol = layers.find((l) => l.type === "symbol")?.id;
      fillIds.current = layers.filter((l) => (l.type === "fill" || l.type === "fill-extrusion") && l.layout?.visibility !== "none").map((l) => l.id);

      map.addSource("usgs", { type: "raster", tiles: [USGS_IMAGERY], tileSize: 256, maxzoom: 16, attribution: "Imagery: USGS The National Map" });
      map.addSource("dem", { type: "raster-dem", tiles: [TERRAIN_TILES], tileSize: 256, encoding: "terrarium", maxzoom: 15, attribution: "Terrain: Mapzen/AWS Terrain Tiles (USGS 3DEP, SRTM)" });
      map.addSource("mask", { type: "geojson", data: EMPTY });
      map.addSource("outline", { type: "geojson", data: EMPTY });
      map.addSource("cells", { type: "geojson", data: EMPTY });
      map.addSource("landmarks", { type: "geojson", data: EMPTY });
      map.addSource("route", { type: "geojson", data: EMPTY });
      map.addSource("route-stops", { type: "geojson", data: EMPTY });
      map.addSource("me", { type: "geojson", data: EMPTY });

      // Imagery sits right above the style's background so every road, river
      // and label stays on top of it; the hillshade goes under the lines.
      map.addLayer({ id: "usgs-imagery", type: "raster", source: "usgs", layout: { visibility: "none" } }, layers[1]?.id);
      map.addLayer({ id: "hillshade", type: "hillshade", source: "dem",
        paint: { "hillshade-exaggeration": 0.55, "hillshade-shadow-color": "#4d4336", "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#6e6a5f" } }, firstLine);
      map.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#f4f3ee", "fill-opacity": 0.7 } }, firstSymbol);
      map.addLayer({ id: "outline", type: "line", source: "outline", paint: { "line-color": "#2f6b3a", "line-width": 2, "line-dasharray": [3, 2] } }, firstSymbol);

      const color: maplibregl.ExpressionSpecification = ["case", [">", ["get", "mp"], 0], "#b86e00", "#2a78d6"];
      // Opacity on a log scale: 1 sighting is faint, 1000 is near-solid, and the
      // jump from 1 to 10 reads the same as 10 to 100.
      const opacity = (scale: number): maplibregl.ExpressionSpecification =>
        ["interpolate", ["linear"], ["log10", ["max", 1, ["get", "count"]]], 0, 0.12 * scale, 1, 0.32 * scale, 2, 0.52 * scale, 3, 0.72 * scale];
      map.addLayer({ id: "cells-coarse", type: "fill", source: "cells", filter: ["==", ["get", "coarsened"], true],
        paint: { "fill-color": color, "fill-opacity": opacity(0.45), "fill-outline-color": "rgba(42,120,214,0.3)" } }, firstSymbol);
      map.addLayer({ id: "cells-fill", type: "fill", source: "cells", filter: ["!=", ["get", "coarsened"], true],
        paint: { "fill-color": color, "fill-opacity": opacity(1), "fill-outline-color": "rgba(255,255,255,0.5)" } }, firstSymbol);
      map.addLayer({ id: "cells-selected", type: "line", source: "cells", filter: ["==", ["get", "cell"], ""],
        paint: { "line-color": "#0b0b0b", "line-width": 2 } }, firstSymbol);
      // The planned route: a cased line so it reads on imagery and on paper-white alike.
      map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.9 } }, firstSymbol);
      map.addLayer({ id: "route-line", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#c2410c", "line-width": 4 } }, firstSymbol);

      // Landmarks: tour stops are numbered and always labelled; the rest are
      // small dots that get a name once you are close enough for it to fit.
      map.addLayer({ id: "landmark-dot", type: "circle", source: "landmarks",
        paint: { "circle-radius": ["case", ["get", "stop"], 7, 4], "circle-color": ["case", ["get", "stop"], "#1f5f8b", "#5f5b52"],
                 "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } });
      const label = (id: string, stopsOnly: boolean, minzoom: number) => map.addLayer({
        id, type: "symbol", source: "landmarks", minzoom, filter: ["==", ["get", "stop"], stopsOnly],
        layout: { "text-field": stopsOnly ? ["concat", ["to-string", ["+", ["get", "tour"], 1]], "  ", ["get", "name"]] : ["get", "name"],
                  "text-font": ["Noto Sans Regular"], "text-size": stopsOnly ? 12.5 : 11, "text-offset": [0, 0.9], "text-anchor": "top",
                  "text-max-width": 9, "text-optional": true },
        paint: { "text-color": stopsOnly ? "#12324a" : "#2b2a26", "text-halo-color": "rgba(255,255,255,0.92)", "text-halo-width": 1.4 },
      });
      label("landmark-label-stops", true, 7);
      label("landmark-label", false, 10.5);
      map.addLayer({ id: "route-stop-dot", type: "circle", source: "route-stops",
        paint: { "circle-radius": 11, "circle-color": "#c2410c", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      map.addLayer({ id: "route-stop-n", type: "symbol", source: "route-stops",
        layout: { "text-field": ["get", "n"], "text-font": ["Noto Sans Bold"], "text-size": 12, "text-allow-overlap": true },
        paint: { "text-color": "#ffffff" } });
      map.addLayer({ id: "me-halo", type: "circle", source: "me", paint: { "circle-radius": 16, "circle-color": "#1a73e8", "circle-opacity": 0.18 } });
      map.addLayer({ id: "me-dot", type: "circle", source: "me", paint: { "circle-radius": 7, "circle-color": "#1a73e8", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5 } });

      // A tall sky so the pitched tour view has a horizon instead of a void.
      map.setSky({ "sky-color": "#a8c8e8", "horizon-color": "#e6edf3", "fog-color": "#dfe6ec", "fog-ground-blend": 0.55,
                   "horizon-fog-blend": 0.8, "sky-horizon-blend": 0.6, "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 10, 1, 12, 0] });

      // One click handler: a landmark wins over the cell under it.
      const hitLayers = ["landmark-dot", "cells-fill", "cells-coarse"];
      map.on("click", (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: hitLayers });
        const lm = hits.find((f) => f.layer.id === "landmark-dot");
        if (lm) {
          const p = lm.properties as { name: string; kind: string; tour: number; url: string };
          if (p.tour >= 0) { tourGoRef.current(p.tour); return; }
          new maplibregl.Popup({ closeButton: false, offset: 10, maxWidth: "240px" }).setLngLat(e.lngLat)
            .setHTML(`<strong>${esc(p.name)}</strong><br><span class="muted">${esc(p.kind)}</span>${p.url ? ` · <a href="${esc(p.url)}" target="_blank" rel="noreferrer">Wikipedia</a>` : ""}`
              + `<br><button class="popup-add small-btn" data-id="${esc(String(lm.properties.id))}">+ Add to route</button>`)
            .addTo(map);
          return;
        }
        const cell = hits.find((f) => f.layer.id.startsWith("cells-"));
        if (cell) selectCellRef.current(String(cell.properties.cell));
      });
      map.on("mousemove", (e) => { map.getCanvas().style.cursor = map.queryRenderedFeatures(e.point, { layers: hitLayers }).length ? "pointer" : ""; });

      mapRef.current = map;
      setReady(true);
    });
    // Popup buttons are plain HTML, so one delegated listener turns "+ Add to
    // route" clicks into store actions.
    const onDocClick = (ev: MouseEvent) => {
      const btn = (ev.target as HTMLElement | null)?.closest?.(".popup-add") as HTMLElement | null;
      if (!btn) return;
      const l = landmarksRef.current?.landmarks.find((x) => x.id === btn.dataset.id);
      if (l) addSiteRef.current({ id: l.id, label: l.name, lon: l.lon, lat: l.lat, kind: l.tour !== undefined ? "stop" : "landmark" });
    };
    document.addEventListener("click", onDocClick);
    // The container reaches its final size after fonts and layout settle; MapLibre
    // sized its canvas earlier. Follow the container, not the first measurement.
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);
    return () => { document.removeEventListener("click", onDocClick); ro.disconnect(); map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cells follow the filters.
  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) (map.getSource("cells") as GeoJSONSource).setData({ type: "FeatureCollection", features });
  }, [ready, features]);

  // The park outline: wash out everything else, frame the park, and stop the
  // visitor from panning off to the rest of the country.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const rings = outerRings(boundary);
    (map.getSource("mask") as GeoJSONSource).setData(rings.length ? maskFC(rings) : EMPTY);
    (map.getSource("outline") as GeoJSONSource).setData(rings.length ? outlineFC(rings) : EMPTY);
    const b = boundsOf(rings) ?? boundsOf(cells?.features.map((f) => f.geometry.coordinates[0]) ?? []);
    boundsRef.current = b;
    map.setMaxBounds(null);
    if (b) {
      map.fitBounds(b, { padding: 36, duration: 0, pitch: 0, bearing: 0 });
      map.setMaxBounds(padBounds(b, MAX_BOUNDS_PAD));
    }
  }, [ready, boundary, cells]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) (map.getSource("landmarks") as GeoJSONSource).setData(landmarksFC(landmarks));
  }, [ready, landmarks]);

  // Terrain view keeps the vector landcover and shades it; satellite view hides
  // the fills so USGS imagery shows through, with roads and labels on top.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const sat = basemap === "satellite";
    map.setLayoutProperty("usgs-imagery", "visibility", sat ? "visible" : "none");
    map.setLayoutProperty("hillshade", "visibility", sat ? "none" : "visible");
    for (const id of fillIds.current) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", sat ? "none" : "visible");
    map.setPaintProperty("mask", "fill-color", sat ? "#0a1016" : "#f4f3ee");
    map.setPaintProperty("mask", "fill-opacity", sat ? 0.55 : 0.7);
  }, [ready, basemap]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) map.setTerrain(terrain3d ? { source: "dem", exaggeration: TERRAIN_EXAGGERATION } : null);
  }, [ready, terrain3d]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("cells-selected")) map.setFilter("cells-selected", ["==", ["get", "cell"], selectedCell ?? ""]);
  }, [selectedCell]);

  // The planned route and its numbered stops; the view frames the whole route.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const r = plan.result;
    (map.getSource("route") as GeoJSONSource).setData(r ? { type: "FeatureCollection", features: r.legs.map((l, i) => ({ type: "Feature", properties: { n: i + 1 }, geometry: { type: "LineString", coordinates: l.coords } })) } : EMPTY);
    (map.getSource("route-stops") as GeoJSONSource).setData(r ? { type: "FeatureCollection", features: r.order.map((s, i) => ({ type: "Feature", properties: { n: String(i + 1), label: s.label }, geometry: { type: "Point", coordinates: [s.lon, s.lat] } })) } : EMPTY);
    if (r && r.legs.length) {
      const pts: Ring = [[r.legs[0].from.lon, r.legs[0].from.lat], ...r.legs.flatMap((l) => l.coords)];
      const b = boundsOf([pts]);
      if (b) map.fitBounds(b, { padding: { top: 60, bottom: 60, left: 360, right: 60 }, pitch: 0, maxZoom: 14, duration: reducedMotion ? 0 : 900 });
    }
  }, [ready, plan.result, reducedMotion]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) (map.getSource("me") as GeoJSONSource).setData(location ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [location.lon, location.lat] } }] } : EMPTY);
  }, [ready, location]);

  // The tour camera: fly to the stop, pitched, facing the next stop. Leaving
  // the tour eases back to the whole park.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!tour.active) {
      if (wasTouring.current && boundsRef.current) {
        map.setPadding({ top: 0, left: 0, right: 0, bottom: 0 });
        map.fitBounds(boundsRef.current, { padding: 36, pitch: 0, bearing: 0, duration: reducedMotion ? 0 : 1200 });
      }
      wasTouring.current = false;
      return;
    }
    wasTouring.current = true;
    const stop = stops[tour.stop];
    if (!stop) return;
    // The stop lands in the band of map above the tour panel, whatever its height.
    const panel = document.querySelector<HTMLElement>(".tour")?.offsetHeight ?? 200;
    map.flyTo({ center: [stop.lon, stop.lat], zoom: STOP_ZOOM, pitch: STOP_PITCH, bearing: stopBearing(stops, tour.stop),
                duration: reducedMotion ? 0 : 2800, essential: true, padding: { top: 0, left: 0, right: 0, bottom: panel + 24 } });
  }, [ready, tour.active, tour.stop, stops, reducedMotion]);

  const options = useMemo(() => {
    const list = (species?.species ?? []).filter((s) => s.suppression?.action !== "exclude");
    const q = query.trim();
    return q ? list.filter((s) => speciesMatches(s, q)).slice(0, 12) : [];
  }, [species, query]);
  const current = species?.species.find((s) => s.scientific_name === speciesFilter);

  return (
    <div className="map-page">
      <div ref={container} className="map" role="region" aria-label="Map of aggregated sightings" />

      <div className="controls" role="group" aria-label="Filters">
        <div className="control view-row">
          {stops.length > 0 && !tour.active && <button className="primary" onClick={startTour}>▶ Take the tour</button>}
          <div className="seg" role="group" aria-label="Basemap">
            <button className={basemap === "terrain" ? "on" : ""} aria-pressed={basemap === "terrain"} onClick={() => setBasemap("terrain")}>Terrain</button>
            <button className={basemap === "satellite" ? "on" : ""} aria-pressed={basemap === "satellite"} onClick={() => setBasemap("satellite")}>Satellite</button>
          </div>
          <button className={"toggle" + (terrain3d ? " on" : "")} aria-pressed={terrain3d} onClick={() => setTerrain3d(!terrain3d)}>3D</button>
          {!plan.open && <button className="toggle" onClick={openPlan}>◎ Plan a visit</button>}
        </div>
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
        {plan.open && <PlanPanel />}
      </div>

      <div className="legend" aria-label="Legend">
        <span><i className="swatch human" /> people saw it</span>
        <span><i className="swatch model" /> includes model-predicted</span>
        <span><i className="dot stop" /> tour stop</span>
        <span><i className="dot" /> landmark</span>
        <span className="muted">Cells ~170 m; larger for sensitive species. Empty means nobody looked.</span>
      </div>

      <CellDetail />
      <Tour />
    </div>
  );
}
