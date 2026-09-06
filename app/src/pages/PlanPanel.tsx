import { useMemo, useState } from "react";
import { directionsUrl, FAR_SNAP_M, fmtKm, fmtTime, MAX_SITES, SPEED_DRIVE_MS, type Site } from "../routing";
import { useStore } from "../store";
import { tourStops } from "../tour";
import type { Landmark } from "../types";

// "Based on my location, which sites do I want to see, and what is the best
// order?" Start from the device's position or a place, tick sites (tour
// stops, any landmark, the busiest cells of the filtered species), pick
// driving or walking, and the router orders them and draws the way. Every
// leg links to OpenStreetMap's directions page for turn-by-turn on the road.
export default function PlanPanel() {
  const { plan, landmarks, cells, speciesFilter, location, locationError, locate, closePlan, addSite, removeSite, setPlanStart, setPlanMode, computePlan, clearPlan, amenities } = useStore();
  const [q, setQ] = useState("");
  const stops = useMemo(() => tourStops(landmarks), [landmarks]);
  // Landmarks first, then named campsites, trailheads, visitor centres and features.
  const found = useMemo(() => {
    const n = q.trim().toLowerCase();
    type Found = { id: string; name: string; kind: string; lon: number; lat: number; tour?: number };
    if (!n) return [] as Found[];
    const lm: Found[] = (landmarks?.landmarks ?? []).filter((l) => l.name.toLowerCase().includes(n)).map((l) => ({ id: l.id, name: l.name, kind: l.kind, lon: l.lon, lat: l.lat, tour: l.tour }));
    const am: Found[] = (amenities?.items ?? []).filter((i) => i.named && i.name.toLowerCase().includes(n)).map((i) => ({ id: i.id, name: i.name, kind: i.kind === "info" ? "visitor centre" : i.sub, lon: i.lon, lat: i.lat }));
    return [...lm, ...am].slice(0, 10);
  }, [landmarks, amenities, q]);
  // The filtered species' three busiest open cells, as places to go and look.
  const hotspots = useMemo<Site[]>(() => {
    if (!cells || !speciesFilter) return [];
    const idx = cells.species_index.findIndex((e) => e.n === speciesFilter);
    if (idx < 0) return [];
    const common = cells.species_index[idx].c ?? speciesFilter;
    return cells.features
      .filter((f) => !f.properties.coarsened)
      .map((f) => ({ f, e: f.properties.sp.find((x) => x[0] === idx) }))
      .filter((x): x is { f: typeof x.f; e: NonNullable<typeof x.e> } => !!x.e)
      .sort((a, b) => b.e[1] - a.e[1]).slice(0, 3)
      .map(({ f, e }) => {
        const [lon, lat] = centroid(f.geometry.coordinates[0]);
        return { id: `cell:${f.properties.cell}`, label: `${common} hotspot · ${e[1].toLocaleString()} sightings`, lon, lat, kind: "cell" as const };
      });
  }, [cells, speciesFilter]);
  const siteOf = (l: Landmark): Site => ({ id: l.id, label: l.name, lon: l.lon, lat: l.lat, kind: l.tour !== undefined ? "stop" : "landmark" });
  const r = plan.result;
  const startIsMe = plan.start?.kind === "me";

  return (
    <div className="plan" role="region" aria-label="Plan a visit">
      <div className="plan-head"><strong>Plan a visit</strong><button className="icon-btn" onClick={closePlan} aria-label="Close planner">×</button></div>

      <div className="plan-row">
        <span className="eyebrow">Start</span>
        <button className={"toggle" + (startIsMe ? " on" : "")} onClick={() => void locate()} aria-pressed={startIsMe}>◎ My location</button>
        <select aria-label="Or start at a place" value={plan.start && !startIsMe ? plan.start.id : ""}
          onChange={(e) => { const l = landmarks?.landmarks.find((x) => x.id === e.target.value); setPlanStart(l ? siteOf(l) : null); }}>
          <option value="">or start at…</option>
          {stops.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          {(landmarks?.landmarks ?? []).filter((l) => l.tour === undefined).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </div>
      {startIsMe && location && <p className="muted small plan-note">Position known to about {Math.round(location.accuracyM).toLocaleString()} m.</p>}
      {locationError && <p className="muted small plan-note">{locationError} Pick a starting place instead.</p>}

      <div className="plan-row">
        <span className="eyebrow">By</span>
        <div className="seg" role="group" aria-label="Travel mode">
          <button className={plan.mode === "drive" ? "on" : ""} aria-pressed={plan.mode === "drive"} onClick={() => setPlanMode("drive")}>Drive</button>
          <button className={plan.mode === "hike" ? "on" : ""} aria-pressed={plan.mode === "hike"} onClick={() => setPlanMode("hike")}>Hike</button>
        </div>
      </div>

      <div className="plan-row wrap">
        <span className="eyebrow">See</span>
        {stops.length > 0 && <button className="ghost small-btn" onClick={() => stops.forEach((s) => addSite(siteOf(s)))}>+ all tour stops</button>}
        {hotspots.map((h) => <button key={h.id} className="ghost small-btn" onClick={() => addSite(h)}>+ {h.label}</button>)}
      </div>
      <div className="search">
        <input type="search" placeholder="Add a landmark…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Add a landmark" autoComplete="off" />
        {found.length > 0 && (
          <ul className="suggest" role="listbox">
            {found.map((l) => (
              <li key={l.id} role="option" aria-selected="false">
                <button onClick={() => { addSite({ id: l.id, label: l.name, lon: l.lon, lat: l.lat, kind: l.tour !== undefined ? "stop" : "landmark" }); setQ(""); }}><span>{l.name}</span><span className="muted small">{l.kind}</span></button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {plan.sites.length > 0 && (
        <ol className="sites" aria-label="Places to see">
          {plan.sites.map((s) => <li key={s.id}><span>{s.label}</span><button className="chip-x" aria-label={`Remove ${s.label}`} onClick={() => removeSite(s.id)}>×</button></li>)}
        </ol>
      )}
      <div className="plan-row">
        <button className="primary" disabled={!plan.start || plan.sites.length === 0 || plan.busy} onClick={() => void computePlan()}>{plan.busy ? "Planning…" : "Plan the best route"}</button>
        {r && <button className="ghost" onClick={clearPlan}>Clear</button>}
        <span className="muted small">{plan.sites.length}/{MAX_SITES}</span>
      </div>
      {!plan.start && plan.sites.length > 0 && <p className="muted small plan-note">Choose a start first.</p>}
      {plan.error && <p className="error small">{plan.error}</p>}

      {r && (
        <div className="legs">
          <p className="legs-total"><strong>{fmtKm(r.distanceM)}</strong> · about {fmtTime(r.seconds)} {r.mode === "drive" ? "driving" : "on foot"} · {r.order.length} {r.order.length === 1 ? "stop" : "stops"}</p>
          <ol>
            {r.legs.map((l, i) => (
              <li key={l.to.id}>
                <span className="leg-n">{i + 1}</span>
                <span className="leg-body">
                  <strong>{l.to.label}</strong><br />
                  <span className="muted small">{fmtKm(l.distanceM)} · {fmtTime(l.seconds)} from {l.from.kind === "me" ? "you" : l.from.label}{(r.snapM[l.to.id] ?? 0) > FAR_SNAP_M ? `; the nearest ${r.mode === "drive" ? "road" : "path"} is ${fmtKm(r.snapM[l.to.id])} from the point` : ""}</span>
                  {" · "}<a className="small" href={directionsUrl(l.from, l.to)} target="_blank" rel="noreferrer">turn-by-turn ↗</a>
                </span>
              </li>
            ))}
          </ol>
          {r.unreachable.length > 0 && <p className="muted small">Not on the {r.mode === "drive" ? "road" : "road or trail"} network from there: {r.unreachable.map((u) => u.label).join(", ")}.</p>}
          <p className="muted small">
            Routes follow OpenStreetMap roads{r.mode === "hike" ? " and trails" : ""} and know nothing of closures or seasons; check{" "}
            <a href="https://www.nps.gov/planyourvisit/index.htm" target="_blank" rel="noreferrer">nps.gov</a> before you go.
            Times assume {r.mode === "drive" ? `${Math.round(SPEED_DRIVE_MS * 2.237)} mph` : "5 km/h"} plus five minutes a stop.
          </p>
        </div>
      )}
    </div>
  );
}

function centroid(ring: number[][]): [number, number] {
  const k = ring.length - 1;
  let x = 0, y = 0;
  for (let i = 0; i < k; i++) { x += ring[i][0]; y += ring[i][1]; }
  return [x / k, y / k];
}
