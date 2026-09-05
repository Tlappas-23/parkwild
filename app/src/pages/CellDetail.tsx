import { useMemo } from "react";
import { useStore } from "../store";

// What was seen in the tapped cell, when, how often, from which source.
export default function CellDetail() {
  const { cells, selectedCell, selectCell, selectSpecies } = useStore();
  const rows = useMemo(
    () => (cells && selectedCell ? cells.features.filter((f) => f.properties.cell === selectedCell).map((f) => f.properties) : []),
    [cells, selectedCell],
  );
  if (!selectedCell) return null;
  const total = rows.reduce((a, r) => a + r.count, 0);
  return (
    <aside className="panel" aria-label="Cell detail">
      <div className="panel-head">
        <strong>{total.toLocaleString()} sightings</strong>
        <button className="link" onClick={() => selectCell(null)} aria-label="Close">close</button>
      </div>
      <p className="muted small">
        Cell {selectedCell}{rows[0]?.coarsened ? " (coarsened for a sensitive species)" : ""}
      </p>
      <ul className="list">
        {rows.sort((a, b) => b.count - a.count).map((r) => (
          <li key={r.species}>
            <button className="link" onClick={() => selectSpecies(r.species)}>{r.common_name ?? r.species}</button>
            <span className="muted small"> {r.count} · {r.first?.slice(0, 4)}–{r.last?.slice(0, 4)}</span>
            {r.human_verified > 0 && <span className="badge human">human</span>}
            {r.model_predicted > 0 && <span className="badge model">model</span>}
          </li>
        ))}
      </ul>
    </aside>
  );
}
