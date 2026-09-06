import { useEffect, useMemo, useState } from "react";
import { speciesPhotos } from "../photos";
import PhotoCredit from "../PhotoCredit";
import { useStore } from "../store";
import { nearbySpecies, TOUR_DWELL_MS, TOUR_RADIUS_M, tourStops } from "../tour";

// The tour bar: one stop at a time, what it is (Wikipedia, credited), and
// which animals people have recorded within walking distance, with a
// photograph each. The camera work lives in MapPage; this is the narration.
//
// The first version was a two-column card that covered a third of the
// screen; the owner's review: "it hides the map, I want it smaller so we
// always see the map". It is now a slim bar with a "Details" toggle for the
// full text and larger photographs.
export default function Tour() {
  const { tour, landmarks, cells, photosSpecies, tourGo, tourNext, tourPrev, tourPlay, endTour, selectSpecies, addSite } = useStore();
  const [expanded, setExpanded] = useState(false);
  const stops = useMemo(() => tourStops(landmarks), [landmarks]);
  const stop = stops[tour.stop];
  const nearby = useMemo(() => (stop ? nearbySpecies(cells, stop.lon, stop.lat) : null), [cells, stop]);

  // Autoplay: dwell, then move on; stops by itself at the last stop.
  useEffect(() => {
    if (!tour.active || !tour.playing) return;
    const t = setTimeout(() => { if (tour.stop < stops.length - 1) tourNext(); else tourPlay(false); }, TOUR_DWELL_MS);
    return () => clearTimeout(t);
  }, [tour.active, tour.playing, tour.stop, stops.length, tourNext, tourPlay]);

  // Arrow keys walk, Escape leaves.
  useEffect(() => {
    if (!tour.active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "ArrowRight") tourNext(); else if (e.key === "ArrowLeft") tourPrev(); else if (e.key === "Escape") endTour();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tour.active, tourNext, tourPrev, endTour]);

  if (!tour.active || !stop) return null;
  const last = tour.stop === stops.length - 1;

  return (
    <section className={"tour" + (expanded ? " expanded" : "")} aria-label="Virtual tour" aria-live="polite">
      <div className="tour-main">
        <div className="tour-title">
          <span className="eyebrow">{tour.stop + 1}/{stops.length} · {stop.kind}{stop.ele_m ? ` · ${Math.round(stop.ele_m).toLocaleString()} m` : ""}</span>
          <h2>{stop.name}</h2>
        </div>
        {stop.summary?.extract ? (
          <p className="tour-text">
            {stop.summary.extract}{" "}
            <a href={stop.summary.url} target="_blank" rel="noreferrer" className="muted small nowrap">Wikipedia, {stop.summary.licence}</a>
          </p>
        ) : stop.url ? (
          <p className="tour-text muted"><a href={stop.url} target="_blank" rel="noreferrer">About {stop.name} on Wikipedia</a></p>
        ) : null}
      </div>

      <div className="tour-wild">
        {nearby && nearby.list.length > 0 ? (
          <ul className="tour-species" aria-label={`Recorded within ${TOUR_RADIUS_M / 1000} km`}>
            {nearby.list.map((n) => {
              const photo = speciesPhotos(photosSpecies, n.species)[0];
              return (
                <li key={n.species}>
                  <button className="tour-card" onClick={() => selectSpecies(n.species)} title={`${n.common ?? n.species}: ${n.count.toLocaleString()} sightings within ${TOUR_RADIUS_M / 1000} km`}>
                    {photo ? <img src={photo.url("square")} alt={`${n.common ?? n.species} photographed by ${photo.observer}`} loading="lazy" /> : <span className="ph" aria-hidden="true" />}
                    <span className="tour-card-name">{n.common ?? n.species}</span>
                    <span className="tour-card-count">{n.count.toLocaleString()}</span>
                  </button>
                  {photo && <PhotoCredit photo={photo} compact />}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="muted small">No open-coordinate sightings near this stop.</p>
        )}
        {nearby && <p className="muted small tour-foot">{nearby.total.toLocaleString()} sightings in {nearby.cells.toLocaleString()} cells within {TOUR_RADIUS_M / 1000} km. Sensitive species are never listed by landmark.</p>}
      </div>

      <div className="tour-nav">
        <button onClick={tourPrev} disabled={tour.stop === 0} aria-label="Previous stop">‹</button>
        <button className="primary" onClick={() => tourPlay(!tour.playing)} aria-pressed={tour.playing}>{tour.playing ? "Pause" : last ? "Replay" : "Play"}</button>
        <button onClick={last ? () => tourGo(0) : tourNext} aria-label={last ? "Back to the first stop" : "Next stop"}>{last ? "↺" : "›"}</button>
        <button className="ghost small-btn" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>{expanded ? "Less" : "Details"}</button>
        <button className="ghost small-btn" onClick={() => addSite({ id: stop.id, label: stop.name, lon: stop.lon, lat: stop.lat, kind: "stop" })} title="Add this stop to a route">+ Route</button>
        <button className="ghost small-btn" onClick={endTour}>Exit</button>
        <div className="dots" role="tablist" aria-label="Stops">
          {stops.map((s, i) => <button key={s.id} role="tab" aria-selected={i === tour.stop} className={i === tour.stop ? "on" : ""} aria-label={`${i + 1}. ${s.name}`} title={s.name} onClick={() => tourGo(i)} />)}
        </div>
      </div>
    </section>
  );
}
