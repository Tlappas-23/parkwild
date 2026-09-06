import { useEffect, useMemo, useState } from "react";
import { speciesPhotos } from "../photos";
import { speciesMatches, useStore } from "../store";
import type { SpeciesAcrossParks } from "../types";
import SpeciesDetail, { shortPark } from "./SpeciesDetail";

// The species page has two scopes. "In this park" is the photo grid the park's
// own files feed. "All parks" searches every shipped park at once from the
// cross-park index, and each row says where the animal turns up and how often,
// so the answer to "where can I see an elk" does not depend on which park
// happens to be open (E-049).
export function indexMatches(e: SpeciesAcrossParks, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [e.c ?? "", e.n, ...e.other].some((n) => n.toLowerCase().includes(needle));
}

// MAX_ROWS — ARBITRARY (735 species across the parks; beyond this the visitor is better off typing)
const MAX_ROWS = 120;

export default function SpeciesPage() {
  const { species, selectedSpecies, selectSpecies, photosSpecies, parkName, speciesScope, setSpeciesScope, speciesIndex, speciesIndexError, ensureSpeciesIndex } = useStore();
  const [query, setQuery] = useState("");
  const [cls, setCls] = useState<"all" | "Mammalia" | "Aves">("all");
  useEffect(() => { if (speciesScope === "all") void ensureSpeciesIndex(); }, [speciesScope, ensureSpeciesIndex]);
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (species?.species ?? []).filter((s) => (cls === "all" || s.class === cls) && speciesMatches(s, q));
  }, [species, query, cls]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (speciesIndex?.species ?? []).filter((e) => (cls === "all" || e.k === cls) && indexMatches(e, q));
  }, [speciesIndex, query, cls]);
  if (!species) return null;
  if (selectedSpecies) {
    const s = species.species.find((x) => x.scientific_name === selectedSpecies) ?? null;
    const entry = speciesIndex?.species.find((e) => e.n === selectedSpecies) ?? null;
    if (s || entry) return <SpeciesDetail species={s} entry={entry} onBack={() => selectSpecies(null)} />;
  }
  const parkCount = speciesIndex ? Object.keys(speciesIndex.parks).length : 0;
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Species</h1>
          <p className="muted">
            {speciesScope === "park"
              ? `${species.species.length} species recorded in ${parkName}, ordered by how often people have seen them.`
              : speciesIndex ? `${speciesIndex.species.length} species across ${parkCount} parks, ordered by sightings. Open one to see where it is seen most, park by park.` : "Loading every park…"}
          </p>
        </div>
        <div className="page-tools">
          <div className="seg" role="group" aria-label="Scope">
            <button className={speciesScope === "park" ? "active" : ""} onClick={() => setSpeciesScope("park")}>In {shortPark(parkName)}</button>
            <button className={speciesScope === "all" ? "active" : ""} onClick={() => setSpeciesScope("all")}>All parks</button>
          </div>
          <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search species" />
          <div className="seg" role="group" aria-label="Class">
            {(["all", "Mammalia", "Aves"] as const).map((c) => (
              <button key={c} className={cls === c ? "active" : ""} onClick={() => setCls(c)}>{c === "all" ? "All" : c === "Mammalia" ? "Mammals" : "Birds"}</button>
            ))}
          </div>
        </div>
      </div>

      {speciesScope === "park" ? (
        <div className="grid" role="list">
          {list.map((s, i) => {
            const photo = speciesPhotos(photosSpecies, s.scientific_name)[0];
            // The first two rows are above the fold on every viewport; lazy-loading them only delays the page's first impression.
            const eager = i < 8;
            return (
              <button key={s.scientific_name} role="listitem" className="card" onClick={() => selectSpecies(s.scientific_name)}>
                <div className="card-media">
                  {photo ? <img src={photo.url("medium")} alt={s.common_name ?? s.scientific_name} loading={eager ? "eager" : "lazy"} /> : <div className="card-empty">{(s.common_name ?? s.scientific_name).slice(0, 1)}</div>}
                  {s.suppression && <span className="pill">{s.suppression.action === "exclude" ? "not mapped" : "mapped coarsely"}</span>}
                </div>
                <div className="card-body">
                  <div className="card-title">{s.common_name ?? s.scientific_name}</div>
                  <div className="muted small"><em>{s.scientific_name}</em></div>
                  <div className="small">{s.sightings.toLocaleString()} sightings</div>
                </div>
              </button>
            );
          })}
        </div>
      ) : speciesIndexError ? (
        <p className="muted">The cross-park index could not be loaded: {speciesIndexError}</p>
      ) : (
        <div className="rows" role="list">
          {rows.slice(0, MAX_ROWS).map((e) => {
            const parks = Object.entries(e.parks).sort((a, b) => b[1].s - a[1].s);
            const shown = parks.slice(0, 4);
            return (
              <button key={e.n} role="listitem" className="row" onClick={() => selectSpecies(e.n)}>
                <div className="row-main">
                  <div className="card-title">{e.c ?? e.n}</div>
                  <div className="muted small"><em>{e.n}</em></div>
                </div>
                <div className="row-parks" aria-label="Parks, most sightings first">
                  {shown.map(([k, p]) => <span key={k} className="chip-park">{shortPark(speciesIndex?.parks[k]?.name ?? k)}<b>{p.s.toLocaleString()}</b></span>)}
                  {parks.length > shown.length && <span className="muted small">+{parks.length - shown.length} more</span>}
                </div>
                <div className="row-total"><strong>{e.total.toLocaleString()}</strong><span className="muted small">in {parks.length} park{parks.length === 1 ? "" : "s"}</span></div>
              </button>
            );
          })}
          {rows.length > MAX_ROWS && <p className="muted small">{rows.length - MAX_ROWS} more match; type to narrow the list.</p>}
          {speciesIndex && rows.length === 0 && <p className="muted">No species matches that in any park.</p>}
        </div>
      )}
    </div>
  );
}
