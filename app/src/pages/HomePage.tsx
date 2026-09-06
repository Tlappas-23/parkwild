import { lazy, Suspense, useState } from "react";
import { useStore } from "../store";
import { PARKS_INDEX } from "../parksIndex";
import type { ParkCard } from "../types";

// The front door: one card per park, live ones first. Counts come from the
// exports; the photograph is the park's Wikipedia lead image, shown only when
// Commons reports a reusable licence, and credited on the card (ADR-0019).
// The overview map pulls in maplibre; it loads after the cards, not before them.
const HomeMap = lazy(() => import("./HomeMap"));
const index = PARKS_INDEX;

function initials(name: string): string {
  return name.replace(/ National Park.*$/, "").split(/\s+/).map((w) => w[0]).join("").slice(0, 3).toUpperCase();
}

export default function HomePage() {
  const { enterPark, park } = useStore();
  const [q, setQ] = useState("");
  const match = (p: ParkCard) => !q.trim() || `${p.name} ${p.state}`.toLowerCase().includes(q.trim().toLowerCase());
  const live = index.parks.filter((p) => p.status === "live" && match(p));
  // The hero is the first live park with a reusable photograph; its credit sits in the corner.
  const heroPark = index.parks.find((p) => p.status === "live" && p.hero) ?? null;
  const planned = index.parks.filter((p) => p.status === "planned" && match(p));
  const seed = index.parks.filter((p) => p.status === "seed" && match(p));

  const card = (p: ParkCard) => (
    <button key={p.key} className={"park-card" + (p.status !== "live" ? " planned" : "") + (p.key === park ? " current" : "")}
      onClick={() => enterPark(p.key)} disabled={p.status !== "live"} aria-label={`${p.name}${p.status !== "live" ? ", coming soon" : ""}`}>
      <div className="park-media">
        {p.hero ? <img src={p.hero.url} alt="" loading="lazy" /> : <div className="park-empty">{initials(p.name)}</div>}
        <span className="park-state">{p.state}</span>
        {p.status === "live" && p.stops ? <span className="park-badge">3D tour · {p.stops} stops</span> : null}
      </div>
      <div className="park-body">
        <h2>{p.name.replace(/ National Park$/, "")}</h2>
        {p.status === "live" ? (
          <p className="muted small">{p.species?.toLocaleString()} species · {p.sightings?.toLocaleString()} sightings · route planner</p>
        ) : (
          <p className="muted small">Coming soon: sightings are being gathered.</p>
        )}
        {p.hero && (
          <p className="credit compact">
            <a href={p.hero.page} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Photo</a>: {p.hero.artist} · {p.hero.license}
          </p>
        )}
      </div>
    </button>
  );

  return (
    <div className="page home">
      <div className="home-hero" style={heroPark?.hero ? { backgroundImage: `url(${heroPark.hero.url})` } : undefined}>
        <h1>Where the animals are.</h1>
        <p className="lede">
          Every recorded sighting in America's national parks, from people who were there, on a 3D map you can tour, filter by species, and plan a route through.
          Pick a park.
        </p>
        <div className="search home-search">
          <input type="search" placeholder="Find a park…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a park" autoComplete="off" autoFocus />
        </div>
        {heroPark?.hero && <p className="credit">{heroPark.name.replace(/ National Park$/, "")} · <a href={heroPark.hero.page} target="_blank" rel="noreferrer">photo</a> {heroPark.hero.artist} · {heroPark.hero.license}</p>}
      </div>
      {live.length === 0 && planned.length === 0 && seed.length === 0 && <p className="muted">No park matches "{q}".</p>}
      <div className="park-grid">{live.map(card)}</div>
      <h2 className="home-sub">Every park on the map</h2>
      <p className="muted small">Filled dots are open; hollow dots are being gathered; faint dots are not started. Click a filled one to go in.</p>
      <Suspense fallback={<div className="home-map placeholder">Loading the map…</div>}><HomeMap parks={index.parks} /></Suspense>
      {planned.length > 0 && (
        <>
          <h2 className="home-sub">Coming soon</h2>
          <div className="park-grid">{planned.map(card)}</div>
        </>
      )}
      {seed.length > 0 && (
        <>
          <h2 className="home-sub">Not started yet · {seed.length} parks</h2>
          <p className="park-names">{seed.map((p) => `${p.name.replace(/ National Park.*$/, "")} (${p.state})`).join(" · ")}</p>
        </>
      )}
      <p className="muted small home-foot">
        Sightings: iNaturalist research-grade observations and other GBIF datasets. Photographs stay with their observers' licences and names.
        Park photographs: Wikimedia Commons, credited on each card. Nothing here is a survey; an empty place means nobody looked.
      </p>
    </div>
  );
}
