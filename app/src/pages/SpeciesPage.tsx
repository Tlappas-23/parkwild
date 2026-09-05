import { useMemo, useState } from "react";
import { speciesPhotos } from "../photos";
import { speciesMatches, useStore } from "../store";
import SpeciesDetail from "./SpeciesDetail";

export default function SpeciesPage() {
  const { species, selectedSpecies, selectSpecies, photosSpecies, parkName } = useStore();
  const [query, setQuery] = useState("");
  const [cls, setCls] = useState<"all" | "Mammalia" | "Aves">("all");
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (species?.species ?? []).filter((s) => (cls === "all" || s.class === cls) &&
      speciesMatches(s, q));
  }, [species, query, cls]);
  if (!species) return null;
  if (selectedSpecies) {
    const s = species.species.find((x) => x.scientific_name === selectedSpecies);
    if (s) return <SpeciesDetail species={s} onBack={() => selectSpecies(null)} />;
  }
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Species</h1>
          <p className="muted">{species.species.length} species recorded in {parkName}, ordered by how often people have seen them.</p>
        </div>
        <div className="page-tools">
          <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search species" />
          <div className="seg" role="group" aria-label="Class">
            {(["all", "Mammalia", "Aves"] as const).map((c) => (
              <button key={c} className={cls === c ? "active" : ""} onClick={() => setCls(c)}>{c === "all" ? "All" : c === "Mammalia" ? "Mammals" : "Birds"}</button>
            ))}
          </div>
        </div>
      </div>
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
    </div>
  );
}
