// Loading and verifying the baked data files.
//
// Integrity: the pipeline writes manifest.json with a SHA-256 per file. The
// copy of the manifest present at build time is compiled into this bundle
// (import.meta.glob below), so a file swapped on the CDN after the build fails
// the hash check and is refused. In development, with no baked manifest, the
// check is skipped and a warning is logged instead of blocking work.
import type { BiasFile, BoundaryFile, CellsFile, LandmarksFile, Manifest, PhotosCellsFile, PhotosSpeciesFile, SpeciesFile } from "./types";

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
  // The manifest hash doubles as a cache key: a rebuild changes the URL, so a
  // browser can never serve last build's file against this build's manifest.
  const expected = manifest?.files[name]?.sha256;
  const url = `${import.meta.env.BASE_URL}data/${park}/${name}` + (expected ? `?v=${expected.slice(0, 16)}` : "");
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  if (expected) {
    const actual = await sha256Hex(buf);
    if (actual !== expected) {
      // Usually this means the app shell is a cached older build and the server
      // has newer data. Ask the service worker for the new build and reload
      // once; only if that does not resolve it is the mismatch shown.
      if (await refreshOnce()) throw new Error("A newer version is available; reloading…");
      throw new Error(`${name} failed its integrity check (expected ${expected.slice(0, 12)}…, got ${actual.slice(0, 12)}…)`);
    }
  } else {
    console.warn(`[parkwild] no baked manifest entry for ${name}; integrity not verified (dev build?)`);
  }
  return JSON.parse(new TextDecoder().decode(buf)) as T;
}

const RELOAD_KEY = "parkwild:integrity-reload";

async function refreshOnce(): Promise<boolean> {
  if (typeof sessionStorage === "undefined" || sessionStorage.getItem(RELOAD_KEY)) return false;
  sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.update()));
      // Drop any cached shell so the reload fetches the build the server has.
      if ("caches" in window) await Promise.all((await caches.keys()).map((k) => caches.delete(k)));
    }
  } catch { /* fall through to a plain reload */ }
  location.reload();
  return true;
}

export async function loadPark(park: string) {
  const manifest = bakedManifest(park);
  const [cells, species, bias, photosSpecies, landmarks, boundary] = await Promise.all([
    fetchVerified<CellsFile>(park, "cells.geojson", manifest),
    fetchVerified<SpeciesFile>(park, "species.json", manifest),
    fetchVerified<BiasFile>(park, "bias.json", manifest).catch(() => null),
    fetchVerified<PhotosSpeciesFile>(park, "photos_species.json", manifest).catch(() => null),
    fetchVerified<LandmarksFile>(park, "landmarks.json", manifest).catch(() => null),      // tour: optional until landmarks ran
    fetchVerified<BoundaryFile>(park, "boundary.geojson", manifest).catch(() => null),
  ]);
  return { cells, species, bias, photosSpecies, landmarks, boundary, manifest };
}

// The per-cell photo file is a megabyte; it is fetched the first time a cell is opened.
export function loadCellPhotos(park: string, manifest: Manifest | null) {
  return fetchVerified<PhotosCellsFile>(park, "photos_cells.json", manifest);
}
