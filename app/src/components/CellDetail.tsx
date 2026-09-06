import { useMemo } from "react";
import WeatherChip from "./WeatherChip";
import { Plus, X } from "lucide-react";
import { cellPhotos, speciesPhotos } from "../lib/photos";
import PhotoCredit from "./PhotoCredit";
import { useStore } from "../store/index";
import type { CellFeature, Species } from "../data/types";

// What was seen in the tapped cell, when, how often, from which source, the
// photographs people took there, and a link to the source observations so
// anyone can check the cell against iNaturalist themselves.
//
// With a species filter on, the drawer is about that species in this cell:
// its count and years, its photographs from this cell, its observation link;
// the other species fold away under "also seen here". The first version
// ignored the filter and answered "what lives here?" when the visitor had
// asked "where are the elk?" (E-024).

// iNaturalist's observation search takes a bounding box; the hexagon's box
// is a little larger than the hexagon, so the page can show a few
// observations from just outside it, and obscured observations appear at
// their public, fuzzed position. That is why the link says "about".
function observationsUrl(feature: CellFeature, taxon: Species | null): string {
  let w = 180,
    e = -180,
    s = 90,
    n = -90;
  for (const [lng, lat] of feature.geometry.coordinates[0]) {
    w = Math.min(w, lng);
    e = Math.max(e, lng);
    s = Math.min(s, lat);
    n = Math.max(n, lat);
  }
  const q = new URLSearchParams({
    nelat: n.toFixed(5),
    nelng: e.toFixed(5),
    swlat: s.toFixed(5),
    swlng: w.toFixed(5),
    quality_grade: "research",
    verifiable: "any",
  });
  if (taxon?.taxon_id) q.set("taxon_id", taxon.taxon_id);
  else if (taxon) q.set("taxon_name", taxon.scientific_name);
  return `https://www.inaturalist.org/observations?${q.toString()}`;
}

export default function CellDetail() {
  const {
    cells,
    species,
    selectedCell,
    selectCell,
    selectSpecies,
    speciesFilter,
    photosCells,
    photosSpecies,
    addSite,
  } = useStore();
  const feature = useMemo(
    () => (cells && selectedCell ? (cells.features.find((f) => f.properties.cell === selectedCell) ?? null) : null),
    [cells, selectedCell],
  );
  // The hexagon's centre, for the weather there.
  const centre = useMemo(() => {
    if (!feature) return null;
    const ring = feature.geometry.coordinates[0];
    let x = 0;
    let y = 0;
    for (const [lng, lat] of ring) {
      x += lng;
      y += lat;
    }
    return [x / ring.length, y / ring.length] as [number, number];
  }, [feature]);
  const allPhotos = useMemo(
    () => (selectedCell ? cellPhotos(photosCells, selectedCell) : []),
    [photosCells, selectedCell],
  );
  // A focused species' photographs from this cell: the cell strip carries one
  // per species, and the species gallery knows which cell each was taken in.
  const focusPhotos = useMemo(() => {
    if (!speciesFilter || !selectedCell) return [];
    const seen = new Set<number>();
    return [
      ...allPhotos.filter((p) => p.species === speciesFilter),
      ...speciesPhotos(photosSpecies, speciesFilter).filter((p) => p.cell === selectedCell),
    ].filter((p) => !seen.has(p.id) && seen.add(p.id));
  }, [allPhotos, photosSpecies, speciesFilter, selectedCell]);
  if (!selectedCell || !feature || !cells) return null;

  const cell = feature.properties;
  const index = cells.species_index;
  const rows = cell.sp
    .map((e) => ({
      species: index[e[0]].n,
      common: index[e[0]].c,
      count: e[1],
      hv: e[2],
      mp: e[3],
      y0: e[4],
      y1: e[5],
    }))
    .sort((a, b) => b.count - a.count);
  const focus = speciesFilter ? (rows.find((r) => r.species === speciesFilter) ?? null) : null;
  const focusMeta = focus ? (species?.species.find((s) => s.scientific_name === focus.species) ?? null) : null;
  const others = focus ? rows.filter((r) => r.species !== focus.species) : rows;
  const photos = focus ? focusPhotos : allPhotos;
  const size = cell.coarsened ? "About 3 km across, coarsened for a sensitive species" : "About 170 m across";

  const strip = (list: typeof photos, label: string) => (
    <div className="strip" aria-label={label}>
      {list.map((p) => (
        <figure key={p.id}>
          <a href={p.observationUrl} target="_blank" rel="noreferrer">
            <img src={p.url("small")} alt={`${p.species ?? "animal"} photographed by ${p.observer}`} loading="lazy" />
          </a>
          <figcaption>
            <strong>{rows.find((r) => r.species === p.species)?.common ?? p.species}</strong>
            {p.date ? ` · ${p.date}` : ""}
            <br />
            <PhotoCredit photo={p} compact />
          </figcaption>
        </figure>
      ))}
    </div>
  );

  const rowList = (list: typeof rows) => (
    <ul className="rows">
      {list.map((r) => (
        <li key={r.species}>
          <button className="row-btn" onClick={() => selectSpecies(r.species)}>
            <span className="row-name">{r.common ?? r.species}</span>
            <span className="row-meta">
              {r.count.toLocaleString()} · {r.y0 ?? "?"}–{r.y1 ?? "?"}
            </span>
            <span className="row-badges">
              {r.hv > 0 && <span className="badge human">verified</span>}
              {r.mp > 0 && <span className="badge model">model</span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <aside className="drawer" aria-label="Cell detail">
      <div className="drawer-head">
        <div>
          <div className="eyebrow">{size}</div>
          {focus ? (
            <>
              <h2>
                {focus.count.toLocaleString()} {focus.common ?? focus.species} sighting{focus.count === 1 ? "" : "s"}{" "}
                here
              </h2>
              <div className="muted small">
                {focus.y0 ?? "?"} to {focus.y1 ?? "?"} · of {cell.count.toLocaleString()} sightings in this cell
              </div>
            </>
          ) : (
            <>
              <h2>{cell.count.toLocaleString()} sightings here</h2>
              {centre && <WeatherChip lat={centre[1]} lon={centre[0]} compact />}
              <div className="muted small">
                {cell.y0 ?? "?"} to {cell.y1 ?? "?"} · {rows.length} species
              </div>
            </>
          )}
        </div>
        <button className="icon-btn" onClick={() => selectCell(null)} aria-label="Close">
          <X className="ico" aria-hidden="true" />
        </button>
      </div>

      {focus && (
        <div className="badges pad">
          {focus.hv > 0 && <span className="badge human">{focus.hv.toLocaleString()} verified by people</span>}
          {focus.mp > 0 && <span className="badge model">{focus.mp.toLocaleString()} model-predicted</span>}
        </div>
      )}

      {photos.length > 0 ? (
        strip(
          photos,
          focus
            ? `Photographs of ${focus.common ?? focus.species} taken in this cell`
            : "Photographs taken in this cell",
        )
      ) : (
        <p className="muted small pad">
          {!photosCells
            ? "Loading photographs…"
            : focus
              ? `No licensed photograph of ${focus.common ?? focus.species} from this cell; the observations themselves are linked below.`
              : "No licensed photographs for this cell; the observations are linked from each species page."}
        </p>
      )}

      {/* Into the route planner as a place to go and look. */}
      <button
        className="ghost small-btn pad-btn"
        onClick={() => {
          const ring = feature.geometry.coordinates[0],
            k = ring.length - 1;
          let x = 0,
            y = 0;
          for (let i = 0; i < k; i++) {
            x += ring[i][0];
            y += ring[i][1];
          }
          addSite({
            id: `cell:${cell.cell}`,
            label: focus
              ? `${focus.common ?? focus.species} spot · ${focus.count.toLocaleString()} sightings`
              : `Wildlife spot · ${cell.count.toLocaleString()} sightings`,
            lon: x / k,
            lat: y / k,
            kind: "cell",
          });
        }}
      >
        <Plus className="ico" aria-hidden="true" /> Add this spot to a route
      </button>

      {/* The check-it-yourself link: the same box, the same species, on the source. */}
      <a className="verify" href={observationsUrl(feature, focusMeta)} target="_blank" rel="noreferrer">
        See {focus ? `${focus.common ?? focus.species} observations` : "the observations"} in about this area on
        iNaturalist ↗
      </a>

      {focus
        ? others.length > 0 && (
            <details className="also">
              <summary>Also recorded in this cell: {others.length} species</summary>
              {rowList(others)}
            </details>
          )
        : rowList(rows)}
    </aside>
  );
}
