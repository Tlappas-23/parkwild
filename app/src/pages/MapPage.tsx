import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type LngLatBoundsLike, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { ChevronDown, ChevronLeft, ChevronUp, Globe, Play, RotateCcw, RotateCw, Route, SlidersHorizontal } from "lucide-react";
import { PARKS_INDEX } from "../parksIndex";
import { addParksLayers, liveBounds, setParksData } from "../parksOverlay";
import type { FeatureCollection } from "geojson";
import { filteredFeatures, speciesMatches, useStore } from "../store";
import { cruisePitch, cruiseZoom, DRIVE_LOOKAHEAD_MIN_M, DRIVE_LOOKAHEAD_PX, DRIVE_MIN_LEG_M, headingAt, legDurationMs, metersPerPixel, ORBIT_DEG_PER_S, ORBIT_PAUSE_MS, placeOf, placeOfLandmark, pointAt, resample, STOP_PITCH, STOP_ZOOM, stopBearing, thingsNear, tourStops, trailLines, type Place } from "../tour";
import { routerFor } from "../routing";
import { esc } from "../html";
import type { BoundaryFile, LandmarksFile, Ring } from "../types";
import CellDetail from "./CellDetail";
import PlaceDetail from "./PlaceDetail";
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
// TERRAIN_EXAGGERATION — ARBITRARY (1 is true relief; on the paper-style map a
// little more reads better at a 60° pitch, on imagery it starts to look wrong)
const TERRAIN_EXAGGERATION = 1.35;
// FOCUS_ZOOM / FOCUS_ZOOM_COARSE — ARBITRARY (landing on a species' busiest cell: a ~170 m hexagon
// with its neighbours in view, or a ~3 km one for a coarsened species)
const FOCUS_ZOOM = 13.8;
const FOCUS_ZOOM_COARSE = 11.2;
const TERRAIN_EXAGGERATION_SATELLITE = 1.12;
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

export default function MapPage() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const fillIds = useRef<string[]>([]);          // the style's own fill layers, hidden under imagery
  const boundsRef = useRef<[[number, number], [number, number]] | null>(null);
  const wasTouring = useRef(false);
  const prevStop = useRef<number | null>(null);          // where the last flight ended, for the drive
  const driving = useRef(false);                          // the orbit yields while the camera is on the road
  const userTouch = useRef(-1e9);        // when the visitor last moved the map themselves
  const fittedPark = useRef<string | null>(null);      // which park the view was last framed on
  const [ready, setReady] = useState(false);
  const [overview, setOverview] = useState(false);          // zoomed out to every park
  const enterParkRef = useRef(useStore.getState().enterPark);
  const {
    cells, species, boundary, landmarks, speciesFilter, yearRange, setSpeciesFilter, setYearRange, selectCell, selectedCell,
    reducedMotion, basemap, setBasemap, terrain3d, setTerrain3d, tour, startTour, tourGo, plan, location, openPlan, addSite, park, cameraPass,
    amenities, tourTab, controlsOpen, setControlsOpen, selectedPlace, selectPlace, roads, showCameraPass, setPage, driveMode, focusCell,
  } = useStore();
  // The amber swatch earns its place only where the camera pass found something.
  const hasModelCells = useMemo(() => (cells?.features ?? []).some((f) => f.properties.mp > 0), [cells]);
  const [query, setQuery] = useState("");
  // Handlers are registered once on the map; refs keep them pointing at the live store actions.
  const selectCellRef = useRef(selectCell); selectCellRef.current = selectCell;
  const tourGoRef = useRef(tourGo); tourGoRef.current = tourGo;
  const addSiteRef = useRef(addSite); addSiteRef.current = addSite;
  const selectPlaceRef = useRef(selectPlace); selectPlaceRef.current = selectPlace;
  const thingsRef = useRef<Map<string, Place>>(new Map());
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
      container: container.current, style: STYLE, center: [-110.5, 44.6], zoom: 7, maxPitch: 78,
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
      map.addSource("corridors", { type: "geojson", data: EMPTY });
      map.addSource("things", { type: "geojson", data: EMPTY });
      map.addSource("focus", { type: "geojson", data: EMPTY });

      // Imagery sits right above the style's background so every road, river
      // and label stays on top of it; the hillshade goes under the lines.
      map.addLayer({ id: "usgs-imagery", type: "raster", source: "usgs", layout: { visibility: "none" } }, layers[1]?.id);
      map.addLayer({ id: "hillshade", type: "hillshade", source: "dem",
        paint: { "hillshade-exaggeration": 0.55, "hillshade-shadow-color": "#4d4336", "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#6e6a5f" } }, firstLine);
      map.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#f4f3ee", "fill-opacity": 0.7 } }, firstSymbol);
      // Where the roadside camera pass ran (or is queued): dashed boxes in the
      // model colour, labelled with what it found, so a zero has a place.
      map.addLayer({ id: "corridor-box", type: "line", source: "corridors",
        paint: { "line-color": "#b86e00", "line-width": 1.6, "line-dasharray": [1.5, 1.5], "line-opacity": ["case", ["==", ["get", "status"], "planned"], 0.5, 0.9] } }, firstSymbol);
      // The park outline: a light casing under a dark dashed line, so it reads
      // on imagery and on the paper-white style alike, at every zoom.
      map.addLayer({ id: "outline-casing", type: "line", source: "outline", paint: { "line-color": "#ffffff", "line-width": 5, "line-opacity": 0.75 } }, firstSymbol);
      map.addLayer({ id: "outline", type: "line", source: "outline", paint: { "line-color": "#14532d", "line-width": 2.5, "line-dasharray": [2.2, 1.4] } }, firstSymbol);

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
        paint: { "line-color": "#1d4ed8", "line-width": 4 } }, firstSymbol);

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
      addParksLayers(map);
      map.addLayer({ id: "corridor-label", type: "symbol", source: "corridors", minzoom: 8,
        layout: { "text-field": ["get", "label"], "text-font": ["Noto Sans Regular"], "text-size": 10.5, "text-anchor": "bottom-left", "text-offset": [0.3, -0.3], "text-max-width": 14 },
        paint: { "text-color": "#8a5200", "text-halo-color": "rgba(255,255,255,0.92)", "text-halo-width": 1.3 } });
      // The open place: a trail drawn whole, or a ring around a point.
      map.addLayer({ id: "focus-casing", type: "line", source: "focus", filter: ["==", ["geometry-type"], "LineString"], layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.9 } });
      map.addLayer({ id: "focus-line", type: "line", source: "focus", filter: ["==", ["geometry-type"], "LineString"], layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#101010", "line-width": 3.5 } });
      map.addLayer({ id: "focus-point", type: "circle", source: "focus", filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 13, "circle-color": "rgba(16,16,16,0.12)", "circle-stroke-color": "#101010", "circle-stroke-width": 2.5 } });
      // Things to do around the current stop, coloured by kind, while that tab is open.
      map.addLayer({ id: "things-dot", type: "circle", source: "things",
        paint: { "circle-radius": 5.5, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5,
                 "circle-color": "#475569" } });
      map.addLayer({ id: "things-label", type: "symbol", source: "things", minzoom: 11,
        layout: { "text-field": ["get", "label"], "text-font": ["Noto Sans Regular"], "text-size": 10.5, "text-offset": [0, 0.8], "text-anchor": "top", "text-optional": true, "text-max-width": 10 },
        paint: { "text-color": "#1f2937", "text-halo-color": "rgba(255,255,255,0.92)", "text-halo-width": 1.2 } });
      map.addLayer({ id: "route-stop-dot", type: "circle", source: "route-stops",
        paint: { "circle-radius": 11, "circle-color": "#1d4ed8", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      map.addLayer({ id: "route-stop-n", type: "symbol", source: "route-stops",
        layout: { "text-field": ["get", "n"], "text-font": ["Noto Sans Bold"], "text-size": 12, "text-allow-overlap": true },
        paint: { "text-color": "#ffffff" } });
      map.addLayer({ id: "me-halo", type: "circle", source: "me", paint: { "circle-radius": 16, "circle-color": "#1a73e8", "circle-opacity": 0.18 } });
      map.addLayer({ id: "me-dot", type: "circle", source: "me", paint: { "circle-radius": 7, "circle-color": "#1a73e8", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5 } });

      // A tall sky so the pitched tour view has a horizon instead of a void.
      map.setSky({ "sky-color": "#a8c8e8", "horizon-color": "#e6edf3", "fog-color": "#dfe6ec", "fog-ground-blend": 0.55,
                   "horizon-fog-blend": 0.8, "sky-horizon-blend": 0.6, "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 10, 1, 12, 0] });

      // A flight that lands before its terrain tile has arrived leaves the
      // camera's target at the wrong height, and MapLibre keeps that height
      // until the next camera move (E-048): the stop is a kilometre below the
      // ground and the screen is fog. Once the map is idle, put it back.
      map.on("idle", () => {
        if (!map.getTerrain() || map.isMoving()) return;
        const q = map.queryTerrainElevation(map.getCenter());
        if (q != null && Number.isFinite(q) && Math.abs(q - map.getCameraTargetElevation()) > 1) map.jumpTo({ elevation: q });
      });

      // One click handler: a landmark wins over the cell under it.
      const hitLayers = ["parks-dot", "things-dot", "landmark-dot", "cells-fill", "cells-coarse"];
      map.on("click", (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: hitLayers });
        const pk = hits.find((f) => f.layer.id === "parks-dot");
        if (pk) {
          const p = pk.properties as { key: string; live: boolean; name: string; status: string };
          if (p.live) { setOverview(false); enterParkRef.current(p.key); }
          else new maplibregl.Popup({ closeButton: false, offset: 10 }).setLngLat(e.lngLat).setHTML(`<strong>${esc(p.name)}</strong><br><span class="muted">${p.status === "planned" ? "sightings are being gathered" : "not started yet"}</span>`).addTo(map);
          return;
        }
        // A thing or a landmark opens the place drawer; a tour stop moves the tour.
        const th = hits.find((f) => f.layer.id === "things-dot");
        if (th) {
          const place = thingsRef.current.get(String(th.properties.id));
          if (place) selectPlaceRef.current(place);
          return;
        }
        const lm = hits.find((f) => f.layer.id === "landmark-dot");
        if (lm) {
          const p = lm.properties as { id: string; tour: number };
          if (p.tour >= 0) { tourGoRef.current(p.tour); return; }
          const l = landmarksRef.current?.landmarks.find((x) => x.id === p.id);
          if (l) selectPlaceRef.current(placeOfLandmark(l));
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
      if (btn.dataset.lon && btn.dataset.lat && btn.dataset.label) {
        addSiteRef.current({ id: `pt:${btn.dataset.lon},${btn.dataset.lat}`, label: btn.dataset.label, lon: +btn.dataset.lon, lat: +btn.dataset.lat, kind: "landmark" });
        return;
      }
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

  // "All parks": drop the pan limit and the wash, show every park, frame the
  // country; entering a park or turning it off brings the park view back.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setParksData(map, overview ? PARKS_INDEX.parks : []);
    map.setLayoutProperty("mask", "visibility", overview ? "none" : "visible");
    if (overview) {
      map.setMaxBounds(null);
      const b = liveBounds(PARKS_INDEX.parks);
      if (b) map.fitBounds(b, { padding: 60, pitch: 0, bearing: 0, maxZoom: 6, duration: reducedMotion ? 0 : 1600 });
    } else if (boundsRef.current) {
      const b = boundsRef.current;
      map.fitBounds(b, { padding: 36, pitch: 0, bearing: 0, duration: reducedMotion ? 0 : 1400 });
      map.once("moveend", () => { if (boundsRef.current === b) map.setMaxBounds(padBounds(b, MAX_BOUNDS_PAD)); });
    }
  }, [ready, overview, reducedMotion]);

  // A park change ends the overview.
  useEffect(() => { setOverview(false); }, [park]);

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
    if (!b || !cells) return;
    // Arrive on the whole park: from a higher, tilted view on first open, or
    // gliding over from the previous park; the pan limit is set once the
    // camera has settled so it cannot clip the approach.
    const cam = map.cameraForBounds(b, { padding: 36 });
    const fast = reducedMotion;
    // Arriving for a species' hotspot (showSpeciesInPark): straight to the cell
    // instead of the whole park.
    const pending = useStore.getState().focusCell;
    if (pending && pending.park === park) {
      useStore.getState().clearFocusCell();
      useStore.getState().selectCell(pending.cell);
      map.flyTo({ center: [pending.lon, pending.lat], zoom: pending.res >= 9 ? FOCUS_ZOOM : FOCUS_ZOOM_COARSE, pitch: 0, bearing: 0, duration: fast ? 0 : 2200, essential: true });
      fittedPark.current = park;
      map.once("moveend", () => { if (boundsRef.current === b) map.setMaxBounds(padBounds(b, MAX_BOUNDS_PAD)); });
      return;
    }
    if (cam) {
      if (fittedPark.current === null) map.jumpTo({ center: cam.center, zoom: (cam.zoom ?? 8) - 1.4, pitch: 38, bearing: -18 });
      map.easeTo({ center: cam.center, zoom: cam.zoom, pitch: 0, bearing: 0, duration: fast ? 0 : fittedPark.current === null ? 1700 : 2200, essential: true });
    }
    fittedPark.current = park;
    map.once("moveend", () => { if (boundsRef.current === b) map.setMaxBounds(padBounds(b, MAX_BOUNDS_PAD)); });
  }, [ready, boundary, cells, park, reducedMotion]);

  // The same hotspot when the park is already in: go there now. (A park
  // switch is handled on arrival, above, which clears the request first.)
  useEffect(() => {
    const map = mapRef.current;
    const pending = useStore.getState().focusCell;
    if (!ready || !map || !cells || !pending || pending.park !== park || fittedPark.current !== park) return;
    useStore.getState().clearFocusCell();
    if (overview) setOverview(false);
    useStore.getState().selectCell(pending.cell);
    map.flyTo({ center: [pending.lon, pending.lat], zoom: pending.res >= 9 ? FOCUS_ZOOM : FOCUS_ZOOM_COARSE, pitch: 0, bearing: 0, duration: reducedMotion ? 0 : 1800, essential: true });
  }, [ready, cells, park, focusCell, overview, reducedMotion]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) (map.getSource("landmarks") as GeoJSONSource).setData(landmarksFC(landmarks));
  }, [ready, landmarks]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const fc: FeatureCollection = {
      type: "FeatureCollection",
      features: (cameraPass?.corridors ?? []).map((c) => {
        const [w, s, e, n] = c.bbox;
        const label = c.status === "planned" ? `Camera pass queued · ${c.name.split(",")[0]}` : `Camera pass · ${c.name.split(",")[0]} · ${c.sightings} sighting${c.sightings === 1 ? "" : "s"}`;
        return { type: "Feature", properties: { key: c.key, status: c.status, label }, geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
      }),
    };
    (map.getSource("corridors") as GeoJSONSource).setData(fc);
  }, [ready, cameraPass]);

  // Terrain view keeps the vector landcover and shades it; satellite view hides
  // the fills so USGS imagery shows through, with roads and labels on top.
  // The country view always uses the drawn map: the imagery service is thin
  // below zoom 5 and a blank continent is not a map.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const sat = basemap === "satellite" && !overview;
    map.setLayoutProperty("usgs-imagery", "visibility", sat ? "visible" : "none");
    map.setLayoutProperty("hillshade", "visibility", sat ? "none" : "visible");
    for (const id of fillIds.current) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", sat ? "none" : "visible");
    map.setPaintProperty("mask", "fill-color", sat ? "#0a1016" : "#f4f3ee");
    map.setPaintProperty("mask", "fill-opacity", sat ? 0.55 : 0.7);
  }, [ready, basemap, overview]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) map.setTerrain(terrain3d ? { source: "dem", exaggeration: basemap === "satellite" ? TERRAIN_EXAGGERATION_SATELLITE : TERRAIN_EXAGGERATION } : null);
  }, [ready, terrain3d, basemap]);

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

  // Markers for the things-to-do tab: the current stop's items, nothing else.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const stop = tour.active && tourTab === "todo" ? stops[tour.stop] : undefined;
    const th = stop ? thingsNear(amenities, stop.lon, stop.lat) : null;
    const all = th ? [...th.features, ...th.trails, ...th.hike, ...th.camp, ...th.stay, ...th.facilities] : [];
    thingsRef.current = new Map(all.map((it) => [it.id, placeOf(it)]));
    (map.getSource("things") as GeoJSONSource).setData({ type: "FeatureCollection", features: all.map((it) => ({
      type: "Feature", properties: { id: it.id, label: it.label, detail: it.detail, kind: it.kind, lon: it.lon, lat: it.lat }, geometry: { type: "Point", coordinates: [it.lon, it.lat] } })) });
  }, [ready, tour.active, tour.stop, tourTab, stops, amenities]);

  // The open place on the map: the whole trail, or a ring; the view moves to it.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const p = selectedPlace;
    if (!p) { (map.getSource("focus") as GeoJSONSource).setData(EMPTY); return; }
    const lines = p.kind === "trail" ? trailLines(roads, p.name) : [];
    const fc: FeatureCollection = { type: "FeatureCollection", features: lines.length
      ? lines.map((l) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: l } }))
      : [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [p.lon, p.lat] } }] };
    (map.getSource("focus") as GeoJSONSource).setData(fc);
    const pad = { top: 60, bottom: 60, left: 60, right: 440 };
    if (lines.length) {
      const b = boundsOf(lines);
      if (b) map.fitBounds(b, { padding: pad, maxZoom: 14.5, duration: reducedMotion ? 0 : 1200 });
    } else {
      map.easeTo({ center: [p.lon, p.lat], zoom: Math.max(map.getZoom(), 13.5), padding: pad, duration: reducedMotion ? 0 : 1000 });
    }
  }, [ready, selectedPlace, roads, reducedMotion]);

  // The tour camera. First stop: fly in and settle close above the place.
  // Every stop after: drive there along the park's own roads from a driver's
  // height, facing the way the road turns, then settle. Leaving the tour eases
  // back to the whole park. Without a road path (a stop off the network, roads
  // not loaded, reduced motion) it flies instead.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!tour.active) {
      if (wasTouring.current && boundsRef.current) {
        map.setPadding({ top: 0, left: 0, right: 0, bottom: 0 });
        map.fitBounds(boundsRef.current, { padding: 36, pitch: 0, bearing: 0, duration: reducedMotion ? 0 : 1200 });
      }
      wasTouring.current = false;
      prevStop.current = null;
      return;
    }
    wasTouring.current = true;
    const stop = stops[tour.stop];
    if (!stop) return;
    const from = prevStop.current !== null && prevStop.current !== tour.stop ? stops[prevStop.current] : null;
    prevStop.current = tour.stop;
    // The stop lands in the map area the tour panel leaves free: beside it on
    // a wide screen, above it on a phone, whatever the panel's size.
    const panel = document.querySelector<HTMLElement>(".tour");
    const side = window.innerWidth >= 900;
    const padding = side ? { top: 0, left: 0, right: (panel?.offsetWidth ?? 300) + 28, bottom: 0 } : { top: 0, left: 0, right: 0, bottom: (panel?.offsetHeight ?? 120) + 24 };
    const arrive = (bearing: number, ms: number) => map.flyTo({ center: [stop.lon, stop.lat], zoom: STOP_ZOOM, pitch: STOP_PITCH, bearing,
      duration: reducedMotion ? 0 : ms, curve: 1.4, essential: true, padding });
    if (!from || reducedMotion || !driveMode) { arrive(stopBearing(stops, tour.stop), from ? 2400 : 3000); return; }

    let cancelled = false;
    let raf = 0;
    const setDrive = useStore.getState().setTourDrive;
    (async () => {
      await useStore.getState().ensureRoads();
      const roads = useStore.getState().roads;
      if (cancelled) return;
      const r = roads ? routerFor(roads) : null;
      const a = r?.snap(from.lon, from.lat, "drive"), b = r?.snap(stop.lon, stop.lat, "drive");
      if (!r || !a || !b || a.node < 0 || b.node < 0 || a.node === b.node) { arrive(stopBearing(stops, tour.stop), 2200); return; }
      const s = r.shortest(a.node, "drive");
      if (s.dist[b.node] === Infinity) { arrive(stopBearing(stops, tour.stop), 2200); return; }
      const coords = r.path(s, b.node);
      if (coords.length < 2) { arrive(stopBearing(stops, tour.stop), 2200); return; }
      const rs = resample(coords, 25);
      if (rs.total < DRIVE_MIN_LEG_M) { arrive(stopBearing(stops, tour.stop), 2200); return; }
      const duration = legDurationMs(rs.total);
      const zoom = cruiseZoom(rs.total, duration, stop.lat);
      const pitch = cruisePitch(zoom);
      const lookM = Math.max(DRIVE_LOOKAHEAD_MIN_M, DRIVE_LOOKAHEAD_PX * metersPerPixel(zoom, stop.lat));
      setDrive({ to: stop.name, distanceM: rs.total });
      driving.current = true;
      map.stop();
      map.setPadding(padding);
      // MapLibre's jumpTo looks the ground up at the zoom it is handed; a
      // fractional zoom finds no terrain tile, the camera's target drops to
      // sea level, a kilometre under the park, and the screen shows fog until
      // something else moves the camera (E-048). So the ground height goes in
      // by hand, from the last terrain tile that has it.
      let ground = map.queryTerrainElevation(rs.pts[0] as [number, number]) ?? map.getCameraTargetElevation();
      const groundAt = (p: [number, number]) => { const q = map.queryTerrainElevation(p); if (q != null && Number.isFinite(q)) ground = q; return ground; };
      // Up to cruising height over the road first, then along it.
      let heading = headingAt(rs, 0, lookM);
      await new Promise<void>((res) => { map.once("moveend", () => res()); map.flyTo({ center: rs.pts[0] as [number, number], zoom, pitch, bearing: heading, duration: 2000, essential: true }); });
      if (cancelled) return;
      const t0 = performance.now();
      let lastNow = t0;
      const frame = (now: number) => {
        if (cancelled) return;
        const t = Math.min(1, (now - t0) / duration);
        const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;      // ease in, ease out
        const d = e * rs.total;
        const p = pointAt(rs, d);
        const target = headingAt(rs, d, lookM);
        const diff = ((target - heading + 540) % 360) - 180;                 // turn the short way, smoothly
        const k = Math.min(1, (now - lastNow) / 120);                         // frame-rate independent smoothing
        lastNow = now;
        heading = heading + diff * k;
        map.jumpTo({ center: p, bearing: heading, pitch, zoom, elevation: groundAt(p) });
        if (t < 1) { raf = requestAnimationFrame(frame); return; }
        driving.current = false;
        setDrive(null);
        arrive(heading, 2000);
      };
      raf = requestAnimationFrame(frame);
    })();
    return () => { cancelled = true; if (raf) cancelAnimationFrame(raf); driving.current = false; setDrive(null); };
  }, [ready, tour.active, tour.stop, stops, reducedMotion, driveMode]);

  // Rotate and tilt from buttons, for everyone who never finds right-drag.
  const turn = (deg: number) => { const m = mapRef.current; if (!m) return; userTouch.current = performance.now(); m.easeTo({ bearing: m.getBearing() + deg, duration: reducedMotion ? 0 : 500 }); };
  const tilt = (deg: number) => { const m = mapRef.current; if (!m) return; userTouch.current = performance.now(); m.easeTo({ pitch: Math.max(0, Math.min(m.getMaxPitch(), m.getPitch() + deg)), duration: reducedMotion ? 0 : 400 }); };

  // The turn around the stop: a frame loop that nudges the bearing whenever
  // the map is not already moving, so it waits for the flight in, yields to
  // a drag or a scroll, and picks up again on its own afterwards. Tapping a
  // cell or a landmark never stops it (E-044).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !tour.active || reducedMotion) return;
    let raf = 0;
    let last = performance.now();
    // A drag, a turn, a tilt, a pinch, a wheel or the rotate buttons all mean
    // "my turn": the orbit waits ORBIT_PAUSE_MS after the last one. Without
    // this it took the map back the moment a finger lifted, which read as "I
    // can't spin the map". A tap is not a view change and does not count
    // (E-050). MapLibre fires rotatestart and pitchstart for its own camera
    // moves as well, so only events carrying a real input event count; the
    // first version counted the orbit's own nudge and paused itself for good
    // (E-048).
    const touched = (e: { originalEvent?: unknown }) => { if (e.originalEvent) userTouch.current = performance.now(); };
    map.on("dragstart", touched); map.on("rotatestart", touched); map.on("pitchstart", touched); map.on("zoomstart", touched); map.on("wheel", touched);
    const tick = (now: number) => {
      const dt = Math.min(now - last, 100);
      last = now;
      const mine = now - userTouch.current > ORBIT_PAUSE_MS;
      if (mine && !driving.current && !map.isMoving()) map.setBearing(map.getBearing() + (ORBIT_DEG_PER_S * dt) / 1000);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      map.off("dragstart", touched); map.off("rotatestart", touched); map.off("pitchstart", touched); map.off("zoomstart", touched); map.off("wheel", touched);
    };
  }, [ready, tour.active, reducedMotion]);

  const options = useMemo(() => {
    const list = (species?.species ?? []).filter((s) => s.suppression?.action !== "exclude");
    const q = query.trim();
    return q ? list.filter((s) => speciesMatches(s, q)).slice(0, 12) : [];
  }, [species, query]);
  const current = species?.species.find((s) => s.scientific_name === speciesFilter);

  return (
    <div className={"map-page" + (tour.active ? " touring" : "")}>
      <div ref={container} className="map" role="region" aria-label="Map of aggregated sightings" />

      {!controlsOpen && (
        <button className="controls-pill" onClick={() => setControlsOpen(true)} aria-label="Show filters and tools">
          <SlidersHorizontal className="ico" aria-hidden="true" /> Filters{current ? <span className="pill-chip">{current.common_name ?? current.scientific_name}</span> : null}{plan.open ? <span className="pill-chip">route</span> : null}
        </button>
      )}
      <div className="controls" role="group" aria-label="Filters" hidden={!controlsOpen}>
        <button className="icon-btn controls-hide" onClick={() => setControlsOpen(false)} aria-label="Hide filters and tools" title="Hide panel"><ChevronLeft className="ico" aria-hidden="true" /></button>
        <div className="control view-row">
          {stops.length > 0 && !tour.active && <button className="primary" onClick={startTour}><Play className="ico" aria-hidden="true" /> Take the tour</button>}
          <div className="seg" role="group" aria-label="Basemap">
            <button className={basemap === "terrain" ? "on" : ""} aria-pressed={basemap === "terrain"} onClick={() => setBasemap("terrain")}>Terrain</button>
            <button className={basemap === "satellite" ? "on" : ""} aria-pressed={basemap === "satellite"} onClick={() => setBasemap("satellite")}>Satellite</button>
          </div>
          <button className={"toggle" + (terrain3d ? " on" : "")} aria-pressed={terrain3d} onClick={() => setTerrain3d(!terrain3d)}>3D</button>
          {!plan.open && <button className="toggle" onClick={openPlan}><Route className="ico" aria-hidden="true" /> Plan a visit</button>}
          <button className={"toggle" + (overview ? " on" : "")} aria-pressed={overview} onClick={() => setOverview((v) => !v)}><Globe className="ico" aria-hidden="true" /> All parks</button>
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

      <div className="cam-ctrl" role="group" aria-label="Rotate and tilt">
        <button className="icon-btn" onClick={() => turn(-45)} aria-label="Rotate left" title="Rotate left (or right-drag the map)"><RotateCcw className="ico" aria-hidden="true" /></button>
        <button className="icon-btn" onClick={() => turn(45)} aria-label="Rotate right" title="Rotate right"><RotateCw className="ico" aria-hidden="true" /></button>
        <button className="icon-btn" onClick={() => tilt(-15)} aria-label="Tilt down" title="Look from higher up"><ChevronUp className="ico" aria-hidden="true" /></button>
        <button className="icon-btn" onClick={() => tilt(15)} aria-label="Tilt up" title="Look from lower down"><ChevronDown className="ico" aria-hidden="true" /></button>
      </div>

      <div className="legend" aria-label="Legend">
        <span><i className="swatch human" /> people saw it</span>
        {hasModelCells && <span><i className="swatch model" /> roadside camera pass <button className="link small" onClick={showCameraPass}>what's that?</button></span>}
        <span><i className="dot stop" /> tour stop</span>
        <span><i className="dot" /> landmark</span>
        {cameraPass && cameraPass.corridors.length > 0 && <span><i className="swatch pass" /> camera pass area</span>}
        <span className="muted">Cells ~170 m; larger for sensitive species. Empty means nobody looked. Rotate with the arrows, a right-drag or two fingers. <button className="link small" onClick={() => setPage("about")}>About the data</button></span>
      </div>

      <CellDetail />
      <PlaceDetail />
      <Tour />
    </div>
  );
}
