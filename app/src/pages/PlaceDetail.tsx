import { useEffect, useMemo, useState } from "react";
import PhotoCredit from "../PhotoCredit";
import { useStore } from "../store";
import { fmtDist, nearbySpecies, photoNear, speciesNearLines, TRAIL_BUFFER_M, trailLines } from "../tour";
import { commonsNear, wikiFind, wikiSummary, type CommonsPhoto, type Summary } from "../wiki";

// One place, opened from the tour card, a map marker or the planner: what it
// is, how long or high it is, what Wikipedia says about it, which animals
// people have recorded there (along the whole trail for a trail, within a
// kilometre for a point) with a photograph each, and licensed photographs of
// the place itself. Everything is credited; nothing is inferred.

// POINT_RADIUS_M — ASSUMED (a viewpoint's or campsite's surroundings; wider than a stop's card, narrower than a valley)
const POINT_RADIUS_M = 1000;

export default function PlaceDetail() {
  const { selectedPlace: p, selectPlace, cells, roads, photosCells, photosSpecies, addSite, selectSpecies, parkName, setSpeciesFilter, setPage } = useStore();
  const [summary, setSummary] = useState<Summary | null | undefined>(undefined);
  const [photos, setPhotos] = useState<CommonsPhoto[] | undefined>(undefined);

  const lines = useMemo(() => (p?.kind === "trail" ? trailLines(roads, p.name) : []), [roads, p]);
  const nearby = useMemo(() => {
    if (!p) return null;
    return p.kind === "trail" ? (lines.length ? speciesNearLines(cells, lines) : null) : nearbySpecies(cells, p.lon, p.lat, POINT_RADIUS_M, 8);
  }, [cells, p, lines]);

  useEffect(() => {
    if (!p) return;
    setSummary(undefined); setPhotos(undefined);
    let live = true;
    (p.wiki ? wikiSummary(p.wiki) : wikiFind(p.name, parkName)).then((s) => { if (live) setSummary(s); }).catch(() => { if (live) setSummary(null); });
    commonsNear(p.lat, p.lon).then((ph) => { if (live) setPhotos(ph); }).catch(() => { if (live) setPhotos([]); });
    return () => { live = false; };
  }, [p, parkName]);

  if (!p) return null;
  const facts: string[] = [];
  if (p.lengthM) facts.push(`${(p.lengthM / 1000).toFixed(1)} km of trail`);
  if (p.tags?.ele) facts.push(`${Math.round(+p.tags.ele).toLocaleString()} m elevation`);
  if (p.tags?.capacity) facts.push(`${p.tags.capacity} sites`);
  if (p.tags?.backcountry === "yes") facts.push("backcountry");
  if (p.tags?.fee) facts.push(p.tags.fee === "no" ? "free" : "fee");
  if (p.tags?.reservation) facts.push(p.tags.reservation === "no" ? "first come, first served" : `reservation ${p.tags.reservation}`);
  if (p.tags?.sac_scale) facts.push(p.tags.sac_scale.replace(/_/g, " "));
  if (p.tags?.surface) facts.push(`${p.tags.surface} surface`);
  if (p.tags?.opening_hours) facts.push(p.tags.opening_hours);
  const kindLabel = p.kind === "info" ? "visitor centre" : p.kind === "stay" ? "lodging" : p.kind === "camp" ? "camping" : p.kind;

  return (
    <aside className="drawer place" aria-label="Place detail">
      <div className="drawer-head">
        <div>
          <div className="eyebrow">{kindLabel}{p.detail && !p.lengthM ? "" : ""}</div>
          <h2>{p.name}</h2>
          {facts.length > 0 && <div className="muted small">{facts.join(" · ")}</div>}
        </div>
        <button className="icon-btn" onClick={() => selectPlace(null)} aria-label="Close">×</button>
      </div>

      <div className="place-actions">
        <button className="primary small-btn" onClick={() => addSite({ id: p.id, label: p.name, lon: p.lon, lat: p.lat, kind: "landmark" })}>+ Add to route</button>
        {p.tags?.website && <a className="ghost small-btn as-btn" href={p.tags.website} target="_blank" rel="noreferrer">Website ↗</a>}
        {summary && <a className="ghost small-btn as-btn" href={summary.url} target="_blank" rel="noreferrer">Wikipedia ↗</a>}
      </div>

      <section className="place-sec">
        <div className="eyebrow">About</div>
        {summary === undefined ? <p className="muted small">Looking it up…</p>
          : summary ? <p className="place-text">{summary.extract} <span className="muted small nowrap">Wikipedia · {summary.title} · CC BY-SA 4.0</span></p>
          : <p className="muted small">No Wikipedia article for this {kindLabel}.{p.tags?.description ? ` OpenStreetMap notes: ${p.tags.description}` : ""}</p>}
      </section>

      <section className="place-sec">
        <div className="eyebrow">{p.kind === "trail" ? `Recorded along the trail (within ${TRAIL_BUFFER_M} m)` : `Recorded within ${fmtDist(POINT_RADIUS_M)}`}</div>
        {p.kind === "trail" && !roads ? <p className="muted small">Loading the trail…</p>
          : nearby && nearby.list.length > 0 ? (
            <>
              <ul className="animal-grid">
                {nearby.list.map((n) => {
                  const hit = photoNear(n.species, nearby.cellIds, photosCells, photosSpecies);
                  return (
                    <li key={n.species}>
                      <button className="tour-card" onClick={() => selectSpecies(n.species)} title={`${n.common ?? n.species}: ${n.count.toLocaleString()} sightings here`}>
                        {hit ? <span className="thumb"><img src={hit.photo.url("square")} alt={`${n.common ?? n.species} photographed by ${hit.photo.observer}`} loading="lazy" />{hit.near && <span className="near-tag">near here</span>}</span> : <span className="ph" aria-hidden="true" />}
                        <span className="tour-card-name">{n.common ?? n.species}</span>
                        <span className="tour-card-count">{n.count.toLocaleString()}</span>
                      </button>
                      {hit && <PhotoCredit photo={hit.photo} compact />}
                    </li>
                  );
                })}
              </ul>
              <p className="muted small">{nearby.total.toLocaleString()} sightings in {nearby.cells.toLocaleString()} cells. Sensitive species are never listed by place.{" "}
                {nearby.list[0] && <button className="link small" onClick={() => { setSpeciesFilter(nearby.list[0].species); setPage("map"); selectPlace(null); }}>Show {nearby.list[0].common ?? nearby.list[0].species} on the map</button>}
              </p>
            </>
          ) : <p className="muted small">No open-coordinate sightings recorded here.</p>}
      </section>

      <section className="place-sec">
        <div className="eyebrow">Photographs of the place</div>
        {photos === undefined ? <p className="muted small">Looking on Wikimedia Commons…</p>
          : photos.length > 0 ? (
            <div className="photo-grid">
              {photos.map((ph) => (
                <figure key={ph.url}>
                  <a href={ph.page} target="_blank" rel="noreferrer"><img src={ph.url} alt={`${p.name}, photographed by ${ph.artist}`} loading="lazy" /></a>
                  <figcaption className="credit compact">{ph.artist} · {ph.license} · {ph.distM} m</figcaption>
                </figure>
              ))}
            </div>
          ) : <p className="muted small">No reusable photographs within {fmtDist(400)} on Wikimedia Commons.</p>}
      </section>
      <p className="muted small pad">Place data © OpenStreetMap contributors. Text from Wikipedia, photographs from Wikimedia Commons, each under the licence shown.</p>
    </aside>
  );
}
