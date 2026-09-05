import { lazy, Suspense } from "react";
import type { Species } from "../types";
import { useStore } from "../store";

const Model3D = lazy(() => import("../Model3D"));
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

export default function SpeciesDetail({ species: s, onBack }: { species: Species; onBack: () => void }) {
  const { reducedMotion, setSpeciesFilter, setPage } = useStore();
  const max = Math.max(1, ...s.months);
  return (
    <article className="detail">
      <button className="link" onClick={onBack}>← all species</button>
      <h2>{s.common_name ?? s.scientific_name}</h2>
      <p className="muted"><em>{s.scientific_name}</em> · {s.class}</p>

      <section className="hero3d" aria-label="3D model">
        {s.model && !reducedMotion ? (
          <Suspense fallback={<div className="placeholder">loading model…</div>}>
            <Model3D url={s.model} />
          </Suspense>
        ) : (
          <div className="placeholder">{s.model ? "static view (reduced motion)" : "3D model not yet sourced"}</div>
        )}
      </section>

      <dl className="facts">
        <dt>Sightings</dt><dd>{s.sightings.toLocaleString()}</dd>
        <dt>Confidence basis</dt>
        <dd>
          <span className="badge human">human-verified {s.confidence_basis.human_verified.toLocaleString()}</span>{" "}
          <span className="badge model">model-predicted {s.confidence_basis.model_predicted.toLocaleString()}</span>
        </dd>
        <dt>Sources</dt>
        <dd>iNaturalist {s.sources.inaturalist.toLocaleString()} · GBIF {s.sources.gbif.toLocaleString()} · imagery {s.sources.mapillary_cv.toLocaleString()}</dd>
        <dt>Locations</dt>
        <dd>{s.open_coordinates.toLocaleString()} mappable · {s.obscured_coordinates.toLocaleString()} with coordinates obscured by the source</dd>
        <dt>Seen</dt><dd>{s.first} to {s.last}</dd>
        {s.suppression && (<><dt>Map treatment</dt><dd>{s.suppression.action === "exclude" ? "Not shown on the map." : `Shown at ~3 km cells.`} {s.suppression.why}</dd></>)}
      </dl>

      <section aria-label="Sightings by month">
        <h3>By month</h3>
        <div className="bars" role="img" aria-label={`Monthly sightings: ${s.months.join(", ")}`}>
          {s.months.map((m, i) => (
            <div key={i} className="bar-col">
              <div className="bar" style={{ height: `${(100 * m) / max}%` }} title={`${MONTHS[i]}: ${m}`} />
              <span className="muted small">{MONTHS[i]}</span>
            </div>
          ))}
        </div>
        <p className="muted small">Reflects when people looked as much as when animals were there.</p>
      </section>

      {s.suppression?.action !== "exclude" && (
        <button onClick={() => { setSpeciesFilter(s.scientific_name); setPage("map"); }}>Show on map</button>
      )}
    </article>
  );
}
