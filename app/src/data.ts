// Loading and verifying the baked data files.
//
// Integrity: the pipeline writes manifest.json with a SHA-256 per file. The
// copy of the manifest present at build time is compiled into this bundle
// (import.meta.glob below), so a file swapped on the CDN after the build fails
// the hash check and is refused. In development, with no baked manifest, the
// check is skipped and a warning is logged instead of blocking work.
import type { AmenitiesFile, BiasFile, BoundaryFile, CameraPassFile, CellsFile, LandmarksFile, Manifest, PhotosCellsFile, PhotosSpeciesFile, RoadsFile, SpeciesFile, SpeciesIndexFile } from "./types";
import { PARKS_INDEX } from "./parksIndex";

const baked = import.meta.glob<Manifest>("../public/data/*/manifest.json", { eager: true, import: "default" });

function bakedManifest(park: string): Manifest | null {
  for (const [path, m] of Object.entries(baked)) {
    if (path.includes(`/data/${park}/`)) return m;
  }
  return null;
}

// The parks this build knows are exactly the data folders baked into it; the
// pipeline writes each park's display name into its manifest, so no second
// list has to be kept in step. Yellowstone stays first as the default.
export function availableParks(): { key: string; name: string; state: string | null }[] {
  const list = Object.entries(baked).map(([path, m]) => {
    const key = path.split("/data/")[1].split("/")[0];
    return { key, name: m.name ?? key, state: m.state ?? null };
  });
  return list.sort((a, b) => (a.key === "yellowstone" ? -1 : b.key === "yellowstone" ? 1 : a.name.localeCompare(b.name)));
}

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function fetchVerified<T>(park: string, name: string, manifest: Manifest | null): Promise<T> {
  return fetchChecked<T>(`data/${park}/${name}`, manifest?.files[name]?.sha256, name);
}

// The cross-park species index sits beside the park folders; its hash rides in
// parks.json, which is baked into the build like the park manifests.
export async function loadSpeciesIndex(): Promise<SpeciesIndexFile> {
  return fetchChecked<SpeciesIndexFile>("data/species_index.json", PARKS_INDEX.species_index?.sha256, "species_index.json");
}

async function fetchChecked<T>(path: string, expected: string | undefined, name: string): Promise<T> {
  // The manifest hash doubles as a cache key: a rebuild changes the URL, so a
  // browser can never serve last build's file against this build's manifest.
  const url = `${import.meta.env.BASE_URL}${path}` + (expected ? `?v=${expected.slice(0, 16)}` : "");
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  if (expected) {
    const actual = await sha256Hex(buf);
    if (actual !== expected) {
      // Usually this means the app shell is a cached older build and the server
      // has newer data. Drop the worker and its caches and come back on a
      // fresh URL; only if that does not resolve it is the mismatch shown.
      if (await refreshOnce()) throw new Error("A newer version is available; reloading…");
      throw new Error(`${name} failed its integrity check (expected ${expected.slice(0, 12)}…, got ${actual.slice(0, 12)}…). `
        + "This usually means a new version was published moments ago.");
    }
  } else {
    console.warn(`[parkwild] no baked manifest entry for ${name}; integrity not verified (dev build?)`);
  }
  return JSON.parse(new TextDecoder().decode(buf)) as T;
}

const RELOAD_KEY = "parkwild:integrity-reload";
// RELOAD_RETRY_MS — ARBITRARY (long enough for a CDN edge to pick up a deploy)
// A second attempt inside this window would only loop; after it, the shell
// the server hands out has almost certainly caught up with its data.
const RELOAD_RETRY_MS = 45_000;
const FRESH_PARAM = "fresh";

// The first version (E-023) asked the worker to update and called
// location.reload(). That still served the old shell when the browser or the
// CDN had index.html cached, so the mismatch came straight back (E-027).
// Now: unregister the worker, drop every cache, and navigate to a URL the
// browser has never seen, which no cache can answer.
async function refreshOnce(): Promise<boolean> {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0);
    if (Date.now() - last < RELOAD_RETRY_MS) return false;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch { return false; }
  await dropWorkerAndCaches();
  freshNavigate();
  return true;
}

async function dropWorkerAndCaches(): Promise<void> {
  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if ("caches" in window) await Promise.all((await caches.keys()).map((k) => caches.delete(k)));
  } catch { /* best effort; the fresh URL alone usually suffices */ }
}

function freshNavigate(): void {
  const u = new URL(location.href);
  u.searchParams.set(FRESH_PARAM, String(Date.now()));
  location.replace(u.toString());
}

// The visitor's own "Reload" button: no retry window, same procedure.
export async function hardReload(): Promise<void> {
  try { sessionStorage.removeItem(RELOAD_KEY); } catch { /* ignore */ }
  await dropWorkerAndCaches();
  freshNavigate();
}

// Once a fresh load succeeded the marker parameter has done its job; take it
// out of the address bar so shared links stay clean.
export function stripFreshParam(): void {
  try {
    const u = new URL(location.href);
    if (!u.searchParams.has(FRESH_PARAM)) return;
    u.searchParams.delete(FRESH_PARAM);
    history.replaceState(null, "", u.toString());
  } catch { /* ignore */ }
}

export async function loadPark(park: string) {
  const manifest = bakedManifest(park);
  const [cells, species, bias, photosSpecies, landmarks, boundary, cameraPass, amenities] = await Promise.all([
    fetchVerified<CellsFile>(park, "cells.geojson", manifest),
    fetchVerified<SpeciesFile>(park, "species.json", manifest),
    fetchVerified<BiasFile>(park, "bias.json", manifest).catch(() => null),
    fetchVerified<PhotosSpeciesFile>(park, "photos_species.json", manifest).catch(() => null),
    fetchVerified<LandmarksFile>(park, "landmarks.json", manifest).catch(() => null),      // tour: optional until landmarks ran
    fetchVerified<BoundaryFile>(park, "boundary.geojson", manifest).catch(() => null),
    fetchVerified<CameraPassFile>(park, "camera_pass.json", manifest).catch(() => null),   // the roadside pass: optional
    fetchVerified<AmenitiesFile>(park, "amenities.json", manifest).catch(() => null),      // things to do: optional
  ]);
  return { cells, species, bias, photosSpecies, landmarks, boundary, cameraPass, amenities, manifest };
}

// The per-cell photo file is a megabyte; it is fetched the first time a cell is opened.
export function loadCellPhotos(park: string, manifest: Manifest | null) {
  return fetchVerified<PhotosCellsFile>(park, "photos_cells.json", manifest);
}

// The road-and-trail graph is the largest file and only a planner needs it.
export function loadRoads(park: string, manifest: Manifest | null) {
  return fetchVerified<RoadsFile>(park, "roads.json", manifest);
}
