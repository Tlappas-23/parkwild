import { useEffect, useMemo } from "react";
import { speciesPhotos } from "../photos";
import PhotoCredit from "../PhotoCredit";
import { useStore } from "../store";
import { nearbySpecies, TOUR_DWELL_MS, TOUR_RADIUS_M, tourStops } from "../tour";

// The tour panel: one stop at a time, what it is (Wikipedia, credited), and
// which animals people have recorded within walking distance of it, with a
// photograph each. The camera work lives in MapPage; this is the narration.
export default function Tour() {
  const { tour, landmarks, cells, photosSpecies, tourGo, tourNext, tourPrev, tourPlay, endTour, selectSpecies } = useStore();
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
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "ArrowRight") tourNext(); else if (e.key === "ArrowLeft") tourPrev(); else if (e.key === "Escape") endTour();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tour.active, tourNext, tourPrev, endTour]);

  if (!tour.active || !stop) return null;
  const last = tour.stop === stops.length - 1;

  return (
    <section className="tour" aria-label="Virtual tour" aria-live="polite">
      <div className="tour-main">
        <div className="eyebrow">Stop {tour.stop + 1} of {stops.length} · {stop.kind}{stop.ele_m ? ` · ${Math.round(stop.ele_m).toLocaleString()} m` : ""}</div>
        <h2>{stop.name}</h2>
        {stop.summary?.extract ? (
          <p className="tour-text">
            {stop.summary.extract}{" "}
            <a href={stop.summary.url} target="_blank" rel="noreferrer" className="muted small nowrap">Wikipedia, {stop.summary.licence}</a>
          </p>
        ) : stop.url ? (
          <p className="tour-text muted"><a href={stop.url} target="_blank" rel="noreferrer">About {stop.name} on Wikipedia</a></p>
        ) : null}
        <div className="tour-nav">
          <button onClick={tourPrev} disabled={tour.stop === 0} aria-label="Previous stop">‹ Back</button>
          <button className="primary" onClick={() => tourPlay(!tour.playing)} aria-pressed={tour.playing}>{tour.playing ? "Pause" : last ? "Replay" : "Play"}</button>
          <button onClick={last ? () => tourGo(0) : tourNext} aria-label={last ? "Back to the first stop" : "Next stop"}>{last ? "Start over" : "Next ›"}</button>
          <div className="dots" role="tablist" aria-label="Stops">
            {stops.map((s, i) => <button key={s.id} role="tab" aria-selected={i === tour.stop} className={i === tour.stop ? "on" : ""} aria-label={`${i + 1}. ${s.name}`} title={s.name} onClick={() => tourGo(i)} />)}
          </div>
          <button className="ghost" onClick={endTour}>Exit tour</button>
        </div>
      </div>
      <div className="tour-wild">
        <div className="eyebrow">Recorded within {TOUR_RADIUS_M / 1000} km</div>
        {nearby && nearby.list.length > 0 ? (
          <ul className="tour-species">
            {nearby.list.map((n) => {
              const photo = speciesPhotos(photosSpecies, n.species)[0];
              return (
                <li key={n.species}>
                  <button className="tour-card" onClick={() => selectSpecies(n.species)} title={`${n.common ?? n.species}: ${n.count.toLocaleString()} sightings nearby`}>
                    {photo ? <img src={photo.url("square")} alt={`${n.common ?? n.species} photographed by ${photo.observer}`} loading="lazy" /> : <span className="ph" aria-hidden="true" />}
                    <span className="tour-card-name">{n.common ?? n.species}</span>
                    <span className="tour-card-count">{n.count.toLocaleString()}{n.mp > 0 ? " · model" : ""}</span>
                  </button>
                  {photo && <PhotoCredit photo={photo} compact />}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="muted small">No open-coordinate sightings recorded near this stop.</p>
        )}
        {nearby && <p className="muted small">{nearby.total.toLocaleString()} sightings in {nearby.cells.toLocaleString()} cells. Sensitive species are never listed by landmark.</p>}
      </div>
    </section>
  );
}
