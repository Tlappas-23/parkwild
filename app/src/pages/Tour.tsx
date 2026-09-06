import { useEffect, useMemo, useState } from "react";
import { Bed, Car, ChevronLeft, ChevronRight, Compass, Eye, Footprints, Info, Maximize2, Minimize2, Minus, Mountain, Pause, Play, Plane, Plus, RotateCcw, Sailboat, Signpost, Tent, UtensilsCrossed, X } from "lucide-react";
import PhotoCredit from "../PhotoCredit";
import { useStore } from "../store";
import { nearbySpecies, photoNear, placeOf, thingsNear, TOUR_DWELL_MS, TOUR_RADIUS_M, tourStops, type NearItem } from "../tour";

// The tour bar: one stop at a time, what it is (Wikipedia, credited), and
// which animals people have recorded within walking distance, with a
// photograph each. The camera work lives in MapPage; this is the narration.
//
// The first version was a two-column card that covered a third of the
// screen; the owner's review: "it hides the map, I want it smaller so we
// always see the map". It is now a slim bar with a "Details" toggle for the
// full text and larger photographs.
export default function Tour() {
  const { tour, landmarks, cells, photosSpecies, photosCells, ensureCellPhotos, tourGo, tourNext, tourPrev, tourPlay, endTour, selectSpecies, addSite, amenities, tourTab, setTourTab, selectPlace, tourDrive, driveMode, setDriveMode } = useStore();
  const [expanded, setExpanded] = useState(false);
  const [minimised, setMinimised] = useState(false);   // a one-line strip: name and arrows, nothing else
  const stops = useMemo(() => tourStops(landmarks), [landmarks]);
  const stop = stops[tour.stop];
  const nearby = useMemo(() => (stop ? nearbySpecies(cells, stop.lon, stop.lat) : null), [cells, stop]);
  const things = useMemo(() => (stop ? thingsNear(amenities, stop.lon, stop.lat) : null), [amenities, stop]);
  const KindIcon = ({ kind }: { kind: string }) => {
    const I = kind === "camp" ? Tent : kind === "stay" ? Bed : kind === "trail" ? Footprints : kind === "trailhead" ? Signpost : kind === "feature" ? Mountain
      : kind === "viewpoint" ? Eye : kind === "picnic" ? UtensilsCrossed : kind === "boat" ? Sailboat : Info;
    return <I className="todo-ico" aria-hidden="true" />;
  };
  const group = (title: string, list: NearItem[]) => list.length > 0 && (
    <div className="todo-group">
      <div className="eyebrow">{title}</div>
      <ul className="todo-list">
        {list.map((it) => (
          <li key={it.id}>
            <KindIcon kind={it.kind} />
            <button className="todo-body as-link" onClick={() => selectPlace(placeOf(it))} title="Open this place"><strong>{it.label}</strong><br /><span className="muted small">{it.detail}</span></button>
            <button className="chip-x add" aria-label={`Add ${it.label} to route`} title="Add to route"
              onClick={() => addSite({ id: it.id, label: it.label, lon: it.lon, lat: it.lat, kind: "landmark" })}><Plus className="ico" aria-hidden="true" /></button>
          </li>
        ))}
      </ul>
    </div>
  );

  // The cell strips hold the photographs taken near each stop; fetch them once.
  useEffect(() => { if (tour.active) void ensureCellPhotos(); }, [tour.active, ensureCellPhotos]);

  // Autoplay: once the camera has arrived, dwell, then move on; stops by
  // itself at the last stop. The dwell does not count while on the road.
  useEffect(() => {
    if (!tour.active || !tour.playing || tourDrive) return;
    const t = setTimeout(() => { if (tour.stop < stops.length - 1) tourNext(); else tourPlay(false); }, TOUR_DWELL_MS);
    return () => clearTimeout(t);
  }, [tour.active, tour.playing, tour.stop, stops.length, tourNext, tourPlay, tourDrive]);

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

  if (minimised) {
    return (
      <section className="tour min" aria-label="Virtual tour" aria-live="polite">
        <button className="icon-btn" onClick={tourPrev} disabled={tour.stop === 0} aria-label="Previous stop"><ChevronLeft className="ico" aria-hidden="true" /></button>
        <button className="tour-min-title" onClick={() => setMinimised(false)} title="Show the stop">
          <span className="eyebrow">{tour.stop + 1}/{stops.length}</span> {stop.name}
        </button>
        <button className="icon-btn" onClick={last ? () => tourGo(0) : tourNext} aria-label={last ? "Back to the first stop" : "Next stop"}>{last ? <RotateCcw className="ico" aria-hidden="true" /> : <ChevronRight className="ico" aria-hidden="true" />}</button>
        <button className="icon-btn" onClick={endTour} aria-label="Exit tour"><X className="ico" aria-hidden="true" /></button>
      </section>
    );
  }

  return (
    <section className={"tour" + (expanded ? " expanded" : "")} aria-label="Virtual tour" aria-live="polite">
      <div className="tour-main">
        <div className="tour-title">
          <span className="eyebrow">{tourDrive ? `On the road · ${(tourDrive.distanceM / 1000).toFixed(1)} km to` : `${tour.stop + 1}/${stops.length} · ${stop.kind}${stop.ele_m ? ` · ${Math.round(stop.ele_m).toLocaleString()} m` : ""}`}</span>
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

      <div className="tour-tabs" role="tablist" aria-label="Stop details">
        <button role="tab" aria-selected={tourTab === "wildlife"} className={tourTab === "wildlife" ? "on" : ""} onClick={() => setTourTab("wildlife")}>Wildlife</button>
        <button role="tab" aria-selected={tourTab === "todo"} className={tourTab === "todo" ? "on" : ""} onClick={() => setTourTab("todo")}>Things to do{things && things.total ? ` · ${things.total}` : ""}</button>
        {((stop.photos?.length ?? 0) > 0 || stop.street) && (
          <button role="tab" aria-selected={tourTab === "photos"} className={tourTab === "photos" ? "on" : ""} onClick={() => setTourTab("photos")}>Photos{stop.photos?.length ? ` · ${stop.photos.length}` : ""}</button>
        )}
      </div>

      {tourTab === "photos" && (
        <div className="tour-photos">
          {stop.street && (
            <a className="street-link" href={stop.street.url} target="_blank" rel="noreferrer">
              <span><Compass className="ico" aria-hidden="true" /> Look around from here on Mapillary</span>
              <span className="muted small">{stop.street.is_pano ? "360° photo" : "street-level photo"} · {stop.street.dist_m} m away{stop.street.captured_at ? ` · ${stop.street.captured_at.slice(0, 4)}` : ""}{stop.street.username ? ` · © ${stop.street.username}` : ""} · {stop.street.license}</span>
            </a>
          )}
          {(stop.photos?.length ?? 0) > 0 ? (
            <div className="photo-grid">
              {stop.photos!.map((p) => (
                <figure key={p.url}>
                  <a href={p.page} target="_blank" rel="noreferrer"><img src={p.url} alt={`${stop.name}, photographed by ${p.artist}`} loading="lazy" /></a>
                  <figcaption className="credit compact">{p.artist} · {p.license} · {p.dist_m} m</figcaption>
                </figure>
              ))}
            </div>
          ) : <p className="muted small">No reusable photographs of this spot on Wikimedia Commons yet.</p>}
          <p className="muted small tour-foot">Photographs from Wikimedia Commons under the licence printed on each; street-level imagery on Mapillary, CC BY-SA 4.0.</p>
        </div>
      )}

      {tourTab === "todo" && (
        <div className="tour-todo">
          {things && things.total > 0 ? (
            <>
              {group("Key features", things.features)}
              {group("Hike", [...things.trails, ...things.hike])}
              {group("Camp", things.camp)}
              {group("Stay", things.stay)}
              {group("Also here", things.facilities)}
              <p className="muted small tour-foot">OpenStreetMap data; fees, capacities and seasons as tagged there. Check nps.gov for current status and reservations.</p>
            </>
          ) : (
            <p className="muted small">{amenities ? "Nothing tagged within reach of this stop." : "Things to do are not exported for this park yet."}</p>
          )}
        </div>
      )}

      <div className="tour-wild" hidden={tourTab !== "wildlife"}>
        {nearby && nearby.list.length > 0 ? (
          <ul className="tour-species" aria-label={`Recorded within ${TOUR_RADIUS_M / 1000} km`}>
            {nearby.list.slice(0, expanded ? 6 : 3).map((n) => {   // one row unless Details is open
              const hit = photoNear(n.species, nearby.cellIds, photosCells, photosSpecies);
              const photo = hit?.photo;
              return (
                <li key={n.species}>
                  <button className="tour-card" onClick={() => selectSpecies(n.species)}
                    title={`${n.common ?? n.species}: ${n.count.toLocaleString()} sightings within ${TOUR_RADIUS_M / 1000} km${hit ? (hit.near ? "; photographed near this stop" : "; photographed elsewhere in the park") : ""}`}>
                    {photo ? <span className="thumb">
                      <img src={photo.url("square")} alt={`${n.common ?? n.species} photographed by ${photo.observer}`} loading="lazy" />
                      {hit?.near && <span className="near-tag">near here</span>}
                    </span> : <span className="ph" aria-hidden="true" />}
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
        <button className="icon-btn" onClick={tourPrev} disabled={tour.stop === 0} aria-label="Previous stop"><ChevronLeft className="ico" aria-hidden="true" /></button>
        <button className="primary" onClick={() => tourPlay(!tour.playing)} aria-pressed={tour.playing}>{tour.playing ? <Pause className="ico" aria-hidden="true" /> : <Play className="ico" aria-hidden="true" />}{tour.playing ? "Pause" : last ? "Replay" : "Play"}</button>
        <button className="icon-btn" onClick={last ? () => tourGo(0) : tourNext} aria-label={last ? "Back to the first stop" : "Next stop"}>{last ? <RotateCcw className="ico" aria-hidden="true" /> : <ChevronRight className="ico" aria-hidden="true" />}</button>
        <button className="icon-btn" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded} aria-label={expanded ? "Less detail" : "More detail"} title={expanded ? "Less" : "Details"}>{expanded ? <Minimize2 className="ico" aria-hidden="true" /> : <Maximize2 className="ico" aria-hidden="true" />}</button>
        <button className={"icon-btn" + (driveMode ? " on" : "")} onClick={() => setDriveMode(!driveMode)} aria-pressed={driveMode} aria-label={driveMode ? "Between stops: drive the road (tap to fly instead)" : "Between stops: fly (tap to drive the road)"} title={driveMode ? "Driving the road between stops" : "Flying between stops"}>{driveMode ? <Car className="ico" aria-hidden="true" /> : <Plane className="ico" aria-hidden="true" />}</button>
        <button className="icon-btn" onClick={() => setMinimised(true)} aria-label="Shrink to a strip" title="Minimise"><Minus className="ico" aria-hidden="true" /></button>
        <button className="icon-btn" onClick={() => addSite({ id: stop.id, label: stop.name, lon: stop.lon, lat: stop.lat, kind: "stop" })} aria-label="Add this stop to a route" title="Add to route"><Plus className="ico" aria-hidden="true" /></button>
        <button className="icon-btn" onClick={endTour} aria-label="Exit tour" title="Exit tour"><X className="ico" aria-hidden="true" /></button>
        <div className="dots" role="tablist" aria-label="Stops">
          {stops.map((s, i) => <button key={s.id} role="tab" aria-selected={i === tour.stop} className={i === tour.stop ? "on" : ""} aria-label={`${i + 1}. ${s.name}`} title={s.name} onClick={() => tourGo(i)} />)}
        </div>
      </div>
    </section>
  );
}
