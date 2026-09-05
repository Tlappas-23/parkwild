import { useMemo } from "react";
import { useStore } from "../store";

// What was seen in the tapped cell, when, how often, from which source.
export default function CellDetail() {
  const { cells, selectedCell, selectCell, selectSpecies } = useStore();
  const cell = useMemo(
    () => (cells && selectedCell ? cells.features.find((f) => f.properties.cell === selectedCell)?.properties ?? null : null),
    [cells, selectedCell],
  );
  if (!selectedCell || !cell || !cells) return null;
  const index = cells.species_index;
  const rows = cell.sp.map((e) => ({ species: index[e[0]].n, common_name: index[e[0]].c, count: e[1], hv: e[2], mp: e[3], y0: e[4], y1: e[5] }));
  const total = cell.count;
  return (
    <aside className="panel" aria-label="Cell detail">
      <div className="panel-head">
        <strong>{total.toLocaleString()} sightings</strong>
        <button className="link" onClick={() => selectCell(null)} aria-label="Close">close</button>
      </div>
      <p className="muted small">
        Cell {selectedCell}{cell.coarsened ? " (about 3 km wide; coarsened for a sensitive species)" : " (about 170 m wide)"}
      </p>
      <ul className="list">
        {rows.sort((a, b) => b.count - a.count).map((r) => (
          <li key={r.species}>
            <button className="link" onClick={() => selectSpecies(r.species)}>{r.common_name ?? r.species}</button>
            <span className="muted small"> {r.count} · {r.y0 ?? "?"}–{r.y1 ?? "?"}</span>
            {r.hv > 0 && <span className="badge human">human</span>}
            {r.mp > 0 && <span className="badge model">model</span>}
          </li>
        ))}
      </ul>
    </aside>
  );
}
