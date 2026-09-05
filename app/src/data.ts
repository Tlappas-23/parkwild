// Loading and verifying the baked data files.
//
// Integrity: the pipeline writes manifest.json with a SHA-256 per file. The
// copy of the manifest present at build time is compiled into this bundle
// (import.meta.glob below), so a file swapped on the CDN after the build fails
// the hash check and is refused. In development, with no baked manifest, the
// check is skipped and a warning is logged instead of blocking work.
import type { BiasFile, CellsFile, Manifest, SpeciesFile } from "./types";

const baked = import.meta.glob<Manifest>("../public/data/*/manifest.json", { eager: true, import: "default" });

function bakedManifest(park: string): Manifest | null {
  for (const [path, m] of Object.entries(baked)) {
    if (path.includes(`/data/${park}/`)) return m;
  }
  return null;
}

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function fetchVerified<T>(park: string, name: string, manifest: Manifest | null): Promise<T> {
  // The manifest hash doubles as a cache key: a rebuild changes the URL, so a
  // browser can never serve last build's file against this build's manifest.
  // (The first version used cache: "force-cache" and tripped its own integrity
  // check on the second build.)
  const expectedHash = manifest?.files[name]?.sha256;
  const url = `/data/${park}/${name}` + (expectedHash ? `?v=${expectedHash.slice(0, 16)}` : "");
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  const expected = expectedHash;
  if (expected) {
    const actual = await sha256Hex(buf);
    if (actual !== expected) throw new Error(`${name} failed its integrity check (expected ${expected.slice(0, 12)}…, got ${actual.slice(0, 12)}…)`);
  } else {
    console.warn(`[parkwild] no baked manifest entry for ${name}; integrity not verified (dev build?)`);
  }
  return JSON.parse(new TextDecoder().decode(buf)) as T;
}

export async function loadPark(park: string): Promise<{ cells: CellsFile; species: SpeciesFile; bias: BiasFile | null; manifest: Manifest | null }> {
  const manifest = bakedManifest(park);
  const [cells, species, bias] = await Promise.all([
    fetchVerified<CellsFile>(park, "cells.geojson", manifest),
    fetchVerified<SpeciesFile>(park, "species.json", manifest),
    // bias.json exists only once the imagery track has been measured; its absence is not an error.
    fetchVerified<BiasFile>(park, "bias.json", manifest).catch(() => null),
  ]);
  return { cells, species, bias, manifest };
}
