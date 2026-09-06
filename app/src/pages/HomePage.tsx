import { useState } from "react";
import { useStore } from "../store";
import type { ParkCard, ParksIndex } from "../types";

// The front door: one card per park, live ones first. Counts come from the
// exports; the photograph is the park's Wikipedia lead image, shown only when
// Commons reports a reusable licence, and credited on the card (ADR-0019).
const index = Object.values(import.meta.glob<ParksIndex>("../../public/data/parks.json", { eager: true, import: "default" }))[0] ?? { generated: "", attribution: "", parks: [] };

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
  const planned = index.parks.filter((p) => p.status !== "live" && match(p));

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
      {live.length === 0 && planned.length === 0 && <p className="muted">No park matches "{q}".</p>}
      <div className="park-grid">{live.map(card)}</div>
      {planned.length > 0 && (
        <>
          <h2 className="home-sub">Coming soon</h2>
          <div className="park-grid">{planned.map(card)}</div>
        </>
      )}
      <p className="muted small home-foot">
        Sightings: iNaturalist research-grade observations and other GBIF datasets. Photographs stay with their observers' licences and names.
        Park photographs: Wikimedia Commons, credited on each card. Nothing here is a survey; an empty place means nobody looked.
      </p>
    </div>
  );
}
