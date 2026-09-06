import { lazy, Suspense, useEffect, useMemo } from "react";
import { ArrowLeft, MapPin } from "lucide-react";
import type { Species, SpeciesAcrossParks } from "../types";
import { speciesPhotos } from "../photos";
import PhotoCredit from "../PhotoCredit";
import { useStore } from "../store";

const Model3D = lazy(() => import("../Model3D"));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "Yellowstone National Park" is the badge; in a row or a button the word
// everyone uses is enough.
export function shortPark(name: string): string {
  return name.replace(/ National Park( and Preserve)?$/, "").replace(/ National Parks$/, "");
}

// Where people see this animal, park by park, from the cross-park index: the
// count, the busiest cell, and a button that opens that park's map on it. The
// open park is marked; a park where the species is not mapped gets its count
// and no button, a coarsened one says so.
function WhereSeen({ entry }: { entry: SpeciesAcrossParks }) {
  const { speciesIndex, park, showSpeciesInPark } = useStore();
  const rows = Object.entries(entry.parks).sort((a, b) => b[1].s - a[1].s);
  const max = Math.max(1, ...rows.map(([, p]) => p.s));
  return (
    <section className="where" aria-labelledby="where-h">
      <h2 id="where-h">Where people see them, park by park</h2>
      <p className="muted small">Sightings recorded in each park and its busiest cell. "Show in" opens that park's map filtered to this species, on that cell.</p>
      <ol className="where-list">
        {rows.map(([k, p]) => {
          const name = shortPark(speciesIndex?.parks[k]?.name ?? k);
          const top = p.top[0];
          return (
            <li key={k} className={"where-row" + (k === park ? " here" : "")}>
              <div className="where-name"><strong>{name}</strong><span className="muted small">{speciesIndex?.parks[k]?.state ?? ""}{k === park ? " · open now" : ""}</span></div>
              <div className="where-bar" aria-hidden="true"><div style={{ width: `${(100 * p.s) / max}%` }} /></div>
              <div className="where-num">
                <strong>{p.s.toLocaleString()}</strong>
                <span className="muted small">{p.x === "exclude" ? "not mapped (sensitive)" : top ? `busiest cell ${top[2].toLocaleString()} · ${p.cells} cell${p.cells === 1 ? "" : "s"}${p.x === "coarsen" ? " · coarse" : ""}` : "no mapped cell"}</span>
              </div>
              {p.x === "exclude" || !top
                ? <span className="muted small">counts only</span>
                : <button className="ghost small" onClick={() => showSpeciesInPark(k, entry.n, top)}><MapPin className="ico" aria-hidden="true" /> Show in {name}</button>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default function SpeciesDetail({ species: s, entry, onBack }: { species: Species | null; entry: SpeciesAcrossParks | null; onBack: () => void }) {
  const { ensureSpeciesIndex, speciesIndex, speciesIndexError, parkName } = useStore();
  useEffect(() => { void ensureSpeciesIndex(); }, [ensureSpeciesIndex]);
  const where = entry
    ? <WhereSeen entry={entry} />
    : speciesIndexError ? <p className="muted small">Other parks could not be loaded: {speciesIndexError}</p>
    : !speciesIndex ? <p className="muted small">Loading other parks…</p> : null;
  if (!s && entry) return <LightDetail entry={entry} onBack={onBack} parkName={parkName} where={where} />;
  if (!s) return null;
  return <FullDetail species={s} entry={entry} onBack={onBack} where={where} />;
}

// A species from another park: the index knows its names and where it is,
// the photographs and months live with the park that recorded it.
function LightDetail({ entry, onBack, parkName, where }: { entry: SpeciesAcrossParks; onBack: () => void; parkName: string; where: React.ReactNode }) {
  const { speciesIndex } = useStore();
  const parks = Object.entries(entry.parks).sort((a, b) => b[1].s - a[1].s);
  const most = parks[0];
  return (
    <article className="page detail">
      <button className="link back" onClick={onBack}><ArrowLeft className="ico" aria-hidden="true" /> All species</button>
      <div className="hero">
        <div className="hero-text">
          <div className="eyebrow">{entry.k === "Aves" ? "Bird" : "Mammal"} · not recorded in {shortPark(parkName)}</div>
          <h1>{entry.c ?? entry.n}</h1>
          <p className="muted"><em>{entry.n}</em>{entry.other.length > 0 && <> · also recorded as {entry.other.slice(0, 4).join(", ")}</>}</p>
          <div className="stats">
            <div><strong>{entry.total.toLocaleString()}</strong><span>sightings, all parks</span></div>
            <div><strong>{parks.length}</strong><span>park{parks.length === 1 ? "" : "s"}</span></div>
            {most && <div><strong>{shortPark(speciesIndex?.parks[most[0]]?.name ?? most[0])}</strong><span>seen most</span></div>}
          </div>
          <p className="muted small">Photographs, months and the map come with the park that recorded it: pick one below.</p>
        </div>
      </div>
      {where}
    </article>
  );
}

function FullDetail({ species: s, entry, onBack, where }: { species: Species; entry: SpeciesAcrossParks | null; onBack: () => void; where: React.ReactNode }) {
  const { reducedMotion, setSpeciesFilter, setPage, photosSpecies, species: all, parkName, showCameraPass, park, showSpeciesInPark } = useStore();
  const photos = useMemo(() => speciesPhotos(photosSpecies, s.scientific_name), [photosSpecies, s.scientific_name]);
  const hero = photos[0];
  const max = Math.max(1, ...s.months);
  const peak = s.months.indexOf(max);
  // Everyone's months are the park's observation effort. Two thirds of all
  // sightings fall in June to August, so the busiest month of nearly every
  // species is June or July (E-031). Dividing this species' share of a month
  // by everyone's share shows when it is seen more than usual: elk in the
  // rut, bison on winter range, ground squirrels emerging in April.
  const effort = useMemo(() => {
    const t = new Array<number>(12).fill(0);
    for (const x of all?.species ?? []) x.months.forEach((m, i) => { t[i] += m; });
    return t;
  }, [all]);
  const effortTotal = effort.reduce((a, b) => a + b, 0);
  const total = s.months.reduce((a, b) => a + b, 0);
  // MIN_FOR_RELATIVE — ARBITRARY (a handful of records makes any month look special)
  const MIN_FOR_RELATIVE = 30;
  const rel = s.months.map((m, i) => (total >= MIN_FOR_RELATIVE && effort[i] ? (m / total) / (effort[i] / effortTotal) : 0));
  const relMax = Math.max(...rel);
  const relPeak = relMax > 0 ? rel.indexOf(relMax) : -1;
  const summerShare = effortTotal ? Math.round((100 * (effort[5] + effort[6] + effort[7])) / effortTotal) : 0;
  // The imagery pass (Track B) ran on one Yellowstone corridor; elsewhere a
  // "model 0" badge would only raise the question it cannot answer.
  const parkHasModel = (all?.species ?? []).some((x) => x.confidence_basis.model_predicted > 0);
  return (
    <article className="page detail">
      <button className="link back" onClick={onBack}><ArrowLeft className="ico" aria-hidden="true" /> All species</button>

      <div className="hero">
        {hero ? (
          <figure className="hero-photo">
            <img src={hero.url("large")} alt={`${s.common_name ?? s.scientific_name}, photographed by ${hero.observer}`} />
            <figcaption><PhotoCredit photo={hero} /></figcaption>
          </figure>
        ) : (
          <div className="hero-photo empty">No licensed photograph yet</div>
        )}
        <div className="hero-text">
          <div className="eyebrow">{s.class === "Aves" ? "Bird" : "Mammal"}{s.suppression ? " · sensitive species" : ""}</div>
          <h1>{s.common_name ?? s.scientific_name}</h1>
          <p className="muted"><em>{s.scientific_name}</em>{s.aliases.length > 0 && <> · also recorded as {s.aliases.join(", ")}</>}</p>
          <div className="stats">
            <div><strong>{s.sightings.toLocaleString()}</strong><span>sightings</span></div>
            <div><strong>{s.first?.slice(0, 4)}–{s.last?.slice(0, 4)}</strong><span>years seen</span></div>
            <div><strong>{MONTHS[peak]}</strong><span>busiest month</span></div>
            <div>
              <strong>{relPeak >= 0 ? `${MONTHS[relPeak]} ×${relMax.toFixed(1)}` : "—"}</strong>
              <span title="This species' share of the month divided by everyone's share of it">seen more than usual</span>
            </div>
          </div>
          <div className="badges">
            <span className="badge human">verified {s.confidence_basis.human_verified.toLocaleString()}</span>
            {parkHasModel && s.confidence_basis.model_predicted > 0 ? (
              <button className="badge model as-link" title="Computer-vision detections in street-level imagery; how the pass works" onClick={showCameraPass}>model {s.confidence_basis.model_predicted.toLocaleString()}</button>
            ) : (
              <button className="link small muted" onClick={showCameraPass}>{parkHasModel ? "roadside camera pass: none of this species" : `no camera pass in ${parkName} yet`} · how it works</button>
            )}
          </div>
          {s.suppression?.action !== "exclude" && (
            <button className="primary" onClick={() => {
              const here = entry?.parks[park];
              if (here?.top[0]) showSpeciesInPark(park, s.scientific_name, here.top[0]);
              else { setSpeciesFilter(s.scientific_name); setPage("map"); }
            }}><MapPin className="ico" aria-hidden="true" /> Show in {shortPark(parkName)}</button>
          )}
        </div>
      </div>

      {where}

      {s.model && (
        <section className="panel3d" aria-label="3D model">
          {!reducedMotion ? (
            <Suspense fallback={<div className="placeholder">loading model…</div>}><Model3D url={`${import.meta.env.BASE_URL}${s.model.url}`} /></Suspense>
          ) : <div className="placeholder">3D view paused (reduced motion)</div>}
          <p className="muted small">3D: <a href={s.model.source} target="_blank" rel="noreferrer">{s.model.title}</a> by {s.model.author}, {s.model.license}</p>
        </section>
      )}

      <section className="two-col">
        <div>
          <h2>When people see them</h2>
          <div className="bars" role="img" aria-label={`Monthly sightings: ${s.months.join(", ")}`}>
            {s.months.map((m, i) => (
              <div key={i} className="bar-col">
                <div className={"bar" + (i === peak ? " peak" : "")} style={{ height: `${(100 * m) / max}%` }} title={`${MONTHS[i]}: ${m}`} />
                <span className="muted small">{MONTHS[i].slice(0, 1)}</span>
              </div>
            ))}
          </div>
          {relPeak >= 0 && (
            <div className="bars rel" role="img" aria-label={`Relative to all sightings by month: ${rel.map((r) => r.toFixed(2)).join(", ")}`}>
              {rel.map((r, i) => (
                <div key={i} className="bar-col">
                  <div className={"bar" + (i === relPeak ? " peak" : "") + (r >= 1 ? " above" : "")} style={{ height: `${(100 * r) / relMax}%` }} title={`${MONTHS[i]}: ×${r.toFixed(2)} vs. everyone`} />
                </div>
              ))}
            </div>
          )}
          <p className="muted small">
            Top: sightings by month, which reflects when people looked as much as when animals were there ({summerShare}% of all {parkName} sightings fall in June to August).
            {relPeak >= 0 ? " Bottom: this species' share of each month divided by everyone's; above 1 (darker) means it is seen more than usual then." : ""}
          </p>
        </div>
        <div>
          <h2>Where the records come from</h2>
          <dl className="facts">
            <dt>iNaturalist</dt><dd>{s.sources.inaturalist.toLocaleString()} research-grade observations</dd>
            <dt>GBIF datasets</dt><dd>{s.sources.gbif.toLocaleString()}</dd>
            <dt>Street-level imagery</dt><dd>{s.sources.mapillary_cv.toLocaleString()} model-predicted</dd>
            <dt>Locations</dt><dd>{s.open_coordinates.toLocaleString()} mappable · {s.obscured_coordinates.toLocaleString()} obscured by the source</dd>
            {s.suppression && (<><dt>Map treatment</dt><dd>{s.suppression.action === "exclude" ? "Not shown on the map. " : "Shown at ~3 km cells. "}{s.suppression.why}</dd></>)}
          </dl>
        </div>
      </section>

      {photos.length > 1 && (
        <section>
          <h2>Photographs</h2>
          <div className="gallery">
            {photos.slice(1).map((p) => (
              <figure key={p.id}>
                <a href={p.observationUrl} target="_blank" rel="noreferrer"><img src={p.url("medium")} alt={`${s.common_name ?? s.scientific_name} by ${p.observer}`} loading="lazy" /></a>
                <figcaption><PhotoCredit photo={p} compact />{p.date ? <span className="muted"> · {p.date}</span> : null}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
