// One store for UI state. Data is loaded once per park; filters are applied
// in selectors so the map and the species pages agree on what "filtered" means.
import { create } from "zustand";
import type { AmenitiesFile, BiasFile, BoundaryFile, CameraPassFile, CellFeature, CellsFile, LandmarksFile, Manifest, PhotosCellsFile, PhotosSpeciesFile, RoadsFile, SpeciesFile } from "./types";
import { availableParks, loadCellPhotos, loadPark, loadRoads } from "./data";
import { MAX_SITES, planRoute, routerFor, type Mode, type PlanResult, type Site } from "./routing";
import type { Place } from "./tour";

export type Page = "home" | "map" | "species" | "ask" | "about";
export type Basemap = "terrain" | "satellite";
export interface TourState { active: boolean; stop: number; playing: boolean; }
export interface Location { lon: number; lat: number; accuracyM: number; }
export interface PlanState { open: boolean; start: Site | null; sites: Site[]; mode: Mode; result: PlanResult | null; error: string | null; busy: boolean; }

interface State {
  park: string;
  parkName: string;
  page: Page;
  cells: CellsFile | null;
  species: SpeciesFile | null;
  bias: BiasFile | null;
  photosSpecies: PhotosSpeciesFile | null;
  photosCells: PhotosCellsFile | null;
  landmarks: LandmarksFile | null;
  boundary: BoundaryFile | null;
  cameraPass: CameraPassFile | null;   // Track B per corridor; null where it never ran
  amenities: AmenitiesFile | null;     // things to do around places; null until exported
  tourTab: "wildlife" | "todo" | "photos";
  setTourTab: (t: "wildlife" | "todo" | "photos") => void;
  controlsOpen: boolean;               // the left panel; folds away during a tour and on request
  selectedPlace: Place | null;         // a trail, feature or campsite open in the drawer
  selectPlace: (p: Place | null) => void;
  controlsBeforeTour: boolean;
  setControlsOpen: (open: boolean) => void;
  manifest: Manifest | null;
  error: string | null;
  speciesFilter: string | null;      // scientific name, or null for all
  yearRange: [number, number];        // inclusive
  selectedCell: string | null;
  selectedSpecies: string | null;
  reducedMotion: boolean;
  basemap: Basemap;
  terrain3d: boolean;
  tour: TourState;
  tourPrevBasemap: Basemap | null;   // what the visitor had before the tour switched to satellite
  tourDrive: { to: string; distanceM: number } | null;   // set while the camera is on the road between stops
  setTourDrive: (d: { to: string; distanceM: number } | null) => void;
  location: Location | null;         // the device's position, only ever asked for on a tap
  locationError: string | null;
  roads: RoadsFile | null;           // loaded on the first route request
  plan: PlanState;
  setPage: (p: Page) => void;
  showCameraPass: () => void;
  setSpeciesFilter: (s: string | null) => void;
  setYearRange: (r: [number, number]) => void;
  selectCell: (c: string | null) => void;
  selectSpecies: (s: string | null) => void;
  setPark: (key: string) => void;
  enterPark: (key: string) => void;    // from a home-page card: switch if needed, then the map
  setBasemap: (b: Basemap) => void;
  setTerrain3d: (on: boolean) => void;
  startTour: () => void;
  endTour: () => void;
  tourGo: (i: number) => void;
  tourNext: () => void;
  tourPrev: () => void;
  tourPlay: (on: boolean) => void;
  locate: () => Promise<void>;
  ensureRoads: () => Promise<void>;
  openPlan: () => void;
  closePlan: () => void;
  addSite: (s: Site) => void;
  removeSite: (id: string) => void;
  setPlanStart: (s: Site | null) => void;
  setPlanMode: (m: Mode) => void;
  computePlan: () => Promise<void>;
  clearPlan: () => void;
  load: () => Promise<void>;
  ensureCellPhotos: () => Promise<void>;
}

export const PARKS = availableParks();
const prefersReduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ?park= makes a link open on the right park; anything unknown falls back to
// the first baked park (Yellowstone).
function initialPark(): string {
  try {
    const q = new URLSearchParams(window.location.search).get("park");
    if (q && PARKS.some((p) => p.key === q)) return q;
  } catch { /* no window */ }
  return PARKS[0]?.key ?? "yellowstone";
}
// A link with ?park= opens that park's map; the bare site opens the home page.
function initialPage(): Page {
  try { return new URLSearchParams(window.location.search).has("park") ? "map" : "home"; } catch { return "home"; }
}
function nameOf(key: string): string { return PARKS.find((p) => p.key === key)?.name ?? key; }
function readBasemap(): Basemap {
  try { return localStorage.getItem("parkwild:basemap") === "satellite" ? "satellite" : "terrain"; } catch { return "terrain"; }
}
const NO_TOUR: TourState = { active: false, stop: 0, playing: false };
const NO_PLAN: PlanState = { open: false, start: null, sites: [], mode: "drive", result: null, error: null, busy: false };

export const useStore = create<State>((set, get) => ({
  park: initialPark(),
  parkName: nameOf(initialPark()),
  page: initialPage(),
  cells: null,
  species: null,
  bias: null,
  photosSpecies: null,
  photosCells: null,
  landmarks: null,
  boundary: null,
  cameraPass: null,
  amenities: null,
  tourTab: "wildlife",
  setTourTab: (tourTab) => set({ tourTab }),
  controlsOpen: typeof window === "undefined" || window.innerWidth >= 900,   // phones start with the map
  controlsBeforeTour: true,
  selectedPlace: null,
  selectPlace: (selectedPlace) => { set({ selectedPlace, selectedCell: selectedPlace ? null : get().selectedCell }); if (selectedPlace) { void get().ensureCellPhotos(); if (selectedPlace.kind === "trail") void get().ensureRoads(); } },
  setControlsOpen: (controlsOpen) => set({ controlsOpen }),
  manifest: null,
  error: null,
  speciesFilter: null,
  yearRange: [1900, 2100],
  selectedCell: null,
  selectedSpecies: null,
  reducedMotion: prefersReduced,
  basemap: readBasemap(),
  terrain3d: !prefersReduced,        // relief on by default; off for people who asked the OS for less motion
  tour: NO_TOUR,
  tourPrevBasemap: null,
  tourDrive: null,
  setTourDrive: (tourDrive) => set({ tourDrive }),
  location: null,
  locationError: null,
  roads: null,
  plan: NO_PLAN,
  setPage: (page) => set({ page, selectedSpecies: page === "species" ? get().selectedSpecies : null }),
  // "How the camera pass works" links land on that section of the About page.
  showCameraPass: () => { set({ page: "about" }); setTimeout(() => document.getElementById("camera-pass")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60); },
  setSpeciesFilter: (speciesFilter) => set({ speciesFilter }),
  setYearRange: (yearRange) => set({ yearRange }),
  selectCell: (selectedCell) => { set({ selectedCell, selectedPlace: selectedCell ? null : get().selectedPlace }); if (selectedCell) void get().ensureCellPhotos(); },
  selectSpecies: (selectedSpecies) => set({ selectedSpecies, page: "species" }),
  // Switching parks drops everything loaded, resets every filter, rewrites the
  // URL so the link is shareable, and loads again.
  setPark: (park) => {
    if (park === get().park || !PARKS.some((p) => p.key === park)) return;
    set({ park, parkName: nameOf(park), cells: null, species: null, bias: null, photosSpecies: null, photosCells: null,
          landmarks: null, boundary: null, cameraPass: null, amenities: null, manifest: null, error: null, speciesFilter: null, selectedCell: null,
          selectedSpecies: null, selectedPlace: null, tour: NO_TOUR, roads: null, plan: { ...NO_PLAN, start: get().plan.start?.kind === "me" ? get().plan.start : null } });
    try { const u = new URL(window.location.href); u.searchParams.set("park", park); window.history.replaceState(null, "", u.toString()); } catch { /* ignore */ }
    void get().load();
  },
  enterPark: (park) => { if (park !== get().park) get().setPark(park); set({ page: "map", selectedSpecies: null }); },
  setBasemap: (basemap) => { set({ basemap }); try { localStorage.setItem("parkwild:basemap", basemap); } catch { /* ignore */ } },
  setTerrain3d: (terrain3d) => set({ terrain3d }),
  // The tour is the 3D walk: relief on and imagery under it, the way a flyover
  // reads; leaving the tour puts the visitor's own basemap choice back.
  // The tour clears the stage: the left panel folds away and comes back on exit.
  startTour: () => set({ tour: { active: true, stop: 0, playing: false }, page: "map", selectedCell: null, terrain3d: true,
                         tourPrevBasemap: get().tour.active ? get().tourPrevBasemap : get().basemap, basemap: "satellite",
                         controlsBeforeTour: get().tour.active ? get().controlsBeforeTour : get().controlsOpen, controlsOpen: false }),
  endTour: () => set({ tour: NO_TOUR, basemap: get().tourPrevBasemap ?? get().basemap, tourPrevBasemap: null, controlsOpen: get().controlsBeforeTour }),
  tourGo: (stop) => set({ tour: { ...get().tour, active: true, stop }, page: "map", selectedCell: null, terrain3d: true,
                          tourPrevBasemap: get().tour.active ? get().tourPrevBasemap : get().basemap, basemap: "satellite",
                          controlsBeforeTour: get().tour.active ? get().controlsBeforeTour : get().controlsOpen, controlsOpen: false }),
  tourNext: () => {
    const n = get().landmarks?.tour.length ?? 0, t = get().tour;
    set({ tour: t.stop < n - 1 ? { ...t, stop: t.stop + 1 } : { ...t, playing: false } });
  },
  tourPrev: () => { const t = get().tour; if (t.stop > 0) set({ tour: { ...t, stop: t.stop - 1 } }); },
  tourPlay: (playing) => set({ tour: { ...get().tour, playing } }),
  // Position is asked for on a tap, never on load; the answer becomes the
  // route's start. Errors are shown in words, not codes.
  locate: () => new Promise<void>((resolve) => {
    if (!("geolocation" in navigator)) { set({ locationError: "This browser has no location service." }); resolve(); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const location = { lon: pos.coords.longitude, lat: pos.coords.latitude, accuracyM: pos.coords.accuracy };
        set({ location, locationError: null, plan: { ...get().plan, start: { id: "me", label: "My location", lon: location.lon, lat: location.lat, kind: "me" }, result: null } });
        resolve();
      },
      (err) => { set({ locationError: err.code === 1 ? "Location permission was refused." : "Location is unavailable right now." }); resolve(); },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    );
  }),
  ensureRoads: async () => {
    if (get().roads) return;
    const park = get().park;
    try {
      const roads = await loadRoads(park, get().manifest);
      if (get().park === park) set({ roads });
    } catch (e) {
      console.warn("[parkwild] roads unavailable:", (e as Error).message);
    }
  },
  openPlan: () => set({ plan: { ...get().plan, open: true } }),
  closePlan: () => set({ plan: { ...get().plan, open: false } }),
  addSite: (site) => {
    const p = get().plan;
    if (p.sites.some((s) => s.id === site.id) || p.sites.length >= MAX_SITES) { set({ plan: { ...p, open: true } }); return; }
    set({ plan: { ...p, open: true, sites: [...p.sites, site], result: null } });
  },
  removeSite: (id) => set({ plan: { ...get().plan, sites: get().plan.sites.filter((s) => s.id !== id), result: null } }),
  setPlanStart: (start) => set({ plan: { ...get().plan, start, result: null } }),
  setPlanMode: (mode) => set({ plan: { ...get().plan, mode, result: null } }),
  computePlan: async () => {
    const p = get().plan;
    if (!p.start || p.sites.length === 0) return;
    set({ plan: { ...p, busy: true, error: null } });
    await get().ensureRoads();
    const roads = get().roads;
    if (!roads) { set({ plan: { ...get().plan, busy: false, error: "No road data for this park yet." } }); return; }
    try {
      const result = planRoute(routerFor(roads), p.start, p.sites, p.mode);
      set({ plan: { ...get().plan, busy: false, result, error: null } });
    } catch (e) {
      set({ plan: { ...get().plan, busy: false, error: (e as Error).message } });
    }
  },
  clearPlan: () => set({ plan: { ...get().plan, result: null } }),
  load: async () => {
    const park = get().park;
    try {
      const { cells, species, bias, photosSpecies, landmarks, boundary, cameraPass, amenities, manifest } = await loadPark(park);
      if (get().park !== park) return;         // the visitor switched parks while this one was loading
      let lo = 2100, hi = 1900;
      for (const f of cells.features) {
        if (f.properties.y0 !== null) lo = Math.min(lo, f.properties.y0);
        if (f.properties.y1 !== null) hi = Math.max(hi, f.properties.y1);
      }
      set({ cells, species, bias, photosSpecies, landmarks, boundary, cameraPass, amenities, manifest, error: null, yearRange: lo <= hi ? [lo, hi] : [1900, 2100] });
    } catch (e) {
      if (get().park === park) set({ error: (e as Error).message });
    }
  },
  ensureCellPhotos: async () => {
    if (get().photosCells) return;
    const park = get().park;
    try {
      const photosCells = await loadCellPhotos(park, get().manifest);
      if (get().park === park) set({ photosCells });
    } catch (e) {
      console.warn("[parkwild] cell photos unavailable:", (e as Error).message);
    }
  },
}));

// A cell is shown if its date span overlaps the year range and, with a species
// filter, if it holds that species; the feature's counts are then swapped for
// that species' own numbers. Cells carry spans, not dates, so overlap is the
// honest test: the cell *may* have sightings in range.
export function filteredFeatures(cells: CellsFile | null, speciesFilter: string | null, yearRange: [number, number]): CellFeature[] {
  if (!cells) return [];
  const [lo, hi] = yearRange;
  const idx = speciesFilter ? cells.species_index.findIndex((e) => e.n === speciesFilter) : -1;
  if (speciesFilter && idx < 0) return [];
  const out: CellFeature[] = [];
  for (const f of cells.features) {
    const p = f.properties;
    if (idx >= 0) {
      const e = p.sp.find((x) => x[0] === idx);
      if (!e) continue;
      const first = e[4] ?? lo, last = e[5] ?? hi;
      if (last < lo || first > hi) continue;
      out.push({ ...f, properties: { ...p, count: e[1], hv: e[2], mp: e[3], y0: e[4], y1: e[5], sp: [e] } });
    } else {
      const first = p.y0 ?? lo, last = p.y1 ?? hi;
      if (last < lo || first > hi) continue;
      out.push(f);
    }
  }
  return out;
}

// Does a species match a search? Common name, the names that lost the vote
// ("elk" finds Wapiti), the scientific name, and its synonyms.
export function speciesMatches(s: { common_name: string | null; other_names?: string[]; scientific_name: string; aliases: string[] }, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [s.common_name ?? "", ...(s.other_names ?? []), s.scientific_name, ...s.aliases].some((n) => n.toLowerCase().includes(needle));
}

// Exposed for automated checks in a real browser (like window.__parkwildMap);
// not part of the UI.
if (typeof window !== "undefined") (window as unknown as { __parkwildStore?: typeof useStore }).__parkwildStore = useStore;
