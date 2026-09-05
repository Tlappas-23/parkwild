import { useMemo } from "react";
import { cellPhotos } from "../photos";
import PhotoCredit from "../PhotoCredit";
import { useStore } from "../store";

// What was seen in the tapped cell, when, how often, from which source, with
// the photographs people took there. Photos are the evidence; the numbers are
// the summary.
export default function CellDetail() {
  const { cells, selectedCell, selectCell, selectSpecies, photosCells } = useStore();
  const cell = useMemo(
    () => (cells && selectedCell ? cells.features.find((f) => f.properties.cell === selectedCell)?.properties ?? null : null),
    [cells, selectedCell],
  );
  const photos = useMemo(() => (selectedCell ? cellPhotos(photosCells, selectedCell) : []), [photosCells, selectedCell]);
  if (!selectedCell || !cell || !cells) return null;
  const index = cells.species_index;
  const rows = cell.sp.map((e) => ({ species: index[e[0]].n, common: index[e[0]].c, count: e[1], hv: e[2], mp: e[3], y0: e[4], y1: e[5] }));

  return (
    <aside className="drawer" aria-label="Cell detail">
      <div className="drawer-head">
        <div>
          <div className="eyebrow">{cell.coarsened ? "About 3 km across, coarsened for a sensitive species" : "About 170 m across"}</div>
          <h2>{cell.count.toLocaleString()} sightings here</h2>
          <div className="muted small">{cell.y0 ?? "?"} to {cell.y1 ?? "?"} · {rows.length} species</div>
        </div>
        <button className="icon-btn" onClick={() => selectCell(null)} aria-label="Close">×</button>
      </div>

      {photos.length > 0 ? (
        <div className="strip" aria-label="Photographs taken in this cell">
          {photos.map((p) => (
            <figure key={p.id}>
              <a href={p.observationUrl} target="_blank" rel="noreferrer">
                <img src={p.url("small")} alt={`${p.species ?? "animal"} photographed by ${p.observer}`} loading="lazy" />
              </a>
              <figcaption>
                <strong>{rows.find((r) => r.species === p.species)?.common ?? p.species}</strong>{p.date ? ` · ${p.date}` : ""}
                <br /><PhotoCredit photo={p} compact />
              </figcaption>
            </figure>
          ))}
        </div>
      ) : (
        <p className="muted small pad">{photosCells ? "No licensed photographs for this cell; the observations are linked from each species page." : "Loading photographs…"}</p>
      )}

      <ul className="rows">
        {rows.sort((a, b) => b.count - a.count).map((r) => (
          <li key={r.species}>
            <button className="row-btn" onClick={() => selectSpecies(r.species)}>
              <span className="row-name">{r.common ?? r.species}</span>
              <span className="row-meta">{r.count.toLocaleString()} · {r.y0 ?? "?"}–{r.y1 ?? "?"}</span>
              <span className="row-badges">
                {r.hv > 0 && <span className="badge human">verified</span>}
                {r.mp > 0 && <span className="badge model">model</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
