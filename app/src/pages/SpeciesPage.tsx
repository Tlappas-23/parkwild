import { useStore } from "../store";
import SpeciesDetail from "./SpeciesDetail";

export default function SpeciesPage() {
  const { species, selectedSpecies, selectSpecies } = useStore();
  if (!species) return null;
  if (selectedSpecies) {
    const s = species.species.find((x) => x.scientific_name === selectedSpecies);
    if (s) return <SpeciesDetail species={s} onBack={() => selectSpecies(null)} />;
  }
  return (
    <div className="species-grid" role="list">
      {species.species.map((s) => (
        <button key={s.scientific_name} role="listitem" className="card" onClick={() => selectSpecies(s.scientific_name)}>
          <div className="card-art" aria-hidden="true">{s.class === "Aves" ? "🐦" : "🦌"}</div>
          <div className="card-title">{s.common_name ?? s.scientific_name}</div>
          <div className="muted small">
            <em>{s.scientific_name}</em> · {s.sightings.toLocaleString()} sightings
          </div>
          {s.suppression && <div className="small note">{s.suppression.action === "exclude" ? "not mapped" : "mapped coarsely"}: sensitive species</div>}
        </button>
      ))}
    </div>
  );
}
