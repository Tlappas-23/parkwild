import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Footprints, MapPin, Mountain, Plus, Signpost, Tent } from "lucide-react";
import PhotoCredit from "../components/PhotoCredit";
import { speciesPhotos } from "../lib/photos";
import {
  busiest,
  groupOf,
  kindLabel,
  MONTHS,
  placeMatches,
  sortPlaces,
  type PlaceGroup,
  type PlaceSort,
} from "../lib/places";
import { useStore } from "../store/index";
import type { LandmarkPhoto, PlaceRec } from "../data/types";
import { commonsNear, wikiFind, wikiSummary, type CommonsPhoto, type Summary } from "../lib/wiki";
import { shortPark } from "../lib/names";
import WeatherChip from "../components/WeatherChip";

// Every named trail, site, campground and facility in the park, sorted by how
// many sightings people recorded within reach of it (the free proxy for
// where visitors go), with when they go; and a page for each, like a species
// page: photographs, what Wikipedia says, the months, the animals seen there,
// and the way to the map and the route planner (E-053).

// MAX_ROWS — ARBITRARY (Yellowstone has 1,800 named places; beyond this the visitor is better off typing or filtering)
const MAX_ROWS = 150;

function Sparkline({ months, peak }: { months: number[]; peak: number | null }) {
  const max = Math.max(1, ...months);
  return (
    <div className="spark" role="img" aria-label={`Sightings by month: ${months.join(", ")}`}>
      {months.map((m, i) => (
        <div
          key={i}
          className={"spark-bar" + (i === peak ? " peak" : "")}
          style={{ height: `${Math.max(6, (100 * m) / max)}%` }}
        />
      ))}
    </div>
  );
}

function KindIcon({ p }: { p: PlaceRec }) {
  const g = groupOf(p);
  const I = g === "trails" ? Footprints : g === "camping" ? Tent : g === "facilities" ? Signpost : Mountain;
  return <I className="ico place-kind-mark" aria-hidden="true" />;
}

function Fact({ p }: { p: PlaceRec }) {
  const parts: string[] = [];
  if (p.length_m) parts.push(`${(p.length_m / 1000).toFixed(p.length_m < 10_000 ? 1 : 0)} km`);
  if (p.ele_m) parts.push(`${Math.round(p.ele_m).toLocaleString()} m`);
  if (p.tags?.fee) parts.push(p.tags.fee === "no" ? "free" : "fee");
  if (p.tags?.reservation)
    parts.push(p.tags.reservation === "required" ? "reservation required" : `reservation ${p.tags.reservation}`);
  return parts.length ? <span className="muted small"> · {parts.join(" · ")}</span> : null;
}

export default function PlacesPage() {
  const { places, placesState, ensurePlaces, landmarks, parkName, selectedPlaceId, selectPlaceId } = useStore();
  useEffect(() => {
    void ensurePlaces();
  }, [ensurePlaces]);
  const [group, setGroup] = useState<PlaceGroup>("all");
  const [sort, setSort] = useState<PlaceSort>("recorded");
  const [query, setQuery] = useState("");
  const photoOf = useMemo(
    () => new Map((landmarks?.landmarks ?? []).map((l) => [l.id, l.photos?.[0] ?? null])),
    [landmarks],
  );
  const list = useMemo(() => {
    if (!places) return [];
    const f = places.places.filter((p) => (group === "all" || groupOf(p) === group) && placeMatches(p, query));
    return sortPlaces(f, sort);
  }, [places, group, sort, query]);
  if (!places) {
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h1>Places</h1>
            <p className="muted">
              {placesState === "missing"
                ? `The places of ${parkName} have not been built yet. They arrive with the park's next data update.`
                : "Loading the park's places…"}
            </p>
          </div>
        </div>
      </div>
    );
  }
  if (selectedPlaceId) {
    const p = places.places.find((x) => x.id === selectedPlaceId);
    if (p) return <PlacePage place={p} onBack={() => selectPlaceId(null)} />;
  }
  const counts = { trails: 0, sites: 0, camping: 0, facilities: 0 };
  for (const p of places.places) counts[groupOf(p)] += 1;
  const withReaders = places.places.some((p) => p.views_pm != null);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Places</h1>
          <p className="muted">
            {places.places.length.toLocaleString()} named trails, sites, campgrounds and facilities in {parkName},
            ordered by how many sightings people recorded within reach of each. That is where observers went, the only
            free measure of where visitors go.
          </p>
        </div>
        <div className="page-tools">
          <input
            type="search"
            placeholder="Search places"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search places"
          />
          <div className="seg" role="group" aria-label="Sort">
            <button className={sort === "recorded" ? "active" : ""} onClick={() => setSort("recorded")}>
              Most recorded
            </button>
            {withReaders && (
              <button className={sort === "readers" ? "active" : ""} onClick={() => setSort("readers")}>
                Most read
              </button>
            )}
            {(group === "all" || group === "trails") && (
              <button className={sort === "longest" ? "active" : ""} onClick={() => setSort("longest")}>
                Longest
              </button>
            )}
            <button className={sort === "az" ? "active" : ""} onClick={() => setSort("az")}>
              A to Z
            </button>
          </div>
        </div>
      </div>
      <div className="seg wrap" role="group" aria-label="Kind">
        {(
          [
            ["all", "All", places.places.length],
            ["trails", "Trails", counts.trails],
            ["sites", "Sites", counts.sites],
            ["camping", "Camping", counts.camping],
            ["facilities", "Facilities", counts.facilities],
          ] as const
        ).map(([g, label, n]) => (
          <button key={g} className={group === g ? "active" : ""} onClick={() => setGroup(g)} disabled={n === 0}>
            {label} <span className="count">{n.toLocaleString()}</span>
          </button>
        ))}
      </div>
      <div className="rows" role="list">
        {list.slice(0, MAX_ROWS).map((p) => {
          const b = busiest(p.near.months);
          const photo = p.src === "landmark" ? photoOf.get(p.id) : null;
          return (
            <button key={p.id} role="listitem" className="row place-row" onClick={() => selectPlaceId(p.id)}>
              <div className="place-thumb">
                {photo ? <img src={photo.url} alt="" loading="lazy" /> : <KindIcon p={p} />}
              </div>
              <div className="row-main">
                <div className="card-title">{p.name}</div>
                <div className="muted small">
                  {kindLabel(p)}
                  <Fact p={p} />
                </div>
              </div>
              <div className="place-when">
                <Sparkline months={p.near.months} peak={b?.peak ?? null} />
                <span className="muted small">
                  {b ? b.label : p.near.n ? "too few records for a season" : "no sightings within reach"}
                </span>
              </div>
              <div className="row-total">
                <strong>{p.near.n.toLocaleString()}</strong>
                <span className="muted small">
                  {p.near.n === 1 ? "sighting" : "sightings"}
                  {p.near.species ? ` · ${p.near.species} species` : ""}
                </span>
                {p.views_pm != null && (
                  <span className="muted small">{p.views_pm.toLocaleString()} readers a month</span>
                )}
              </div>
            </button>
          );
        })}
        {list.length > MAX_ROWS && (
          <p className="muted small">{(list.length - MAX_ROWS).toLocaleString()} more; type to narrow the list.</p>
        )}
        {list.length === 0 && <p className="muted">Nothing matches.</p>}
      </div>
      <p className="muted small">
        {places.notes.popularity} {places.notes.months} Places: OpenStreetMap contributors, ODbL.
      </p>
    </div>
  );
}

function PlacePage({ place: p, onBack }: { place: PlaceRec; onBack: () => void }) {
  const { landmarks, species, photosSpecies, parkName, selectPlace, setPage, addSite, selectSpecies, places } =
    useStore();
  const climate = useStore((st) => st.climate);
  const lm = useMemo(() => landmarks?.landmarks.find((l) => l.id === p.id) ?? null, [landmarks, p.id]);
  const [summary, setSummary] = useState<Summary | null | undefined>(
    lm?.summary?.extract ? { title: lm.name, extract: lm.summary.extract, url: lm.summary.url } : undefined,
  );
  const [photos, setPhotos] = useState<(CommonsPhoto | LandmarkPhoto)[] | undefined>(
    lm?.photos?.length ? lm.photos : undefined,
  );
  useEffect(() => {
    let live = true;
    if (summary === undefined) {
      (p.url ? wikiSummary(decodeURIComponent(p.url.split("/wiki/")[1] ?? p.name)) : wikiFind(p.name, parkName))
        .then((s) => {
          if (live) setSummary(s);
        })
        .catch(() => {
          if (live) setSummary(null);
        });
    }
    if (photos === undefined)
      commonsNear(p.lat, p.lon)
        .then((ph) => {
          if (live) setPhotos(ph);
        })
        .catch(() => {
          if (live) setPhotos([]);
        });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.id]);
  const hero = photos?.[0] ?? null;
  const b = busiest(p.near.months);
  const max = Math.max(1, ...p.near.months);
  const total = p.near.months.reduce((a, c) => a + c, 0);
  const byName = useMemo(() => new Map((species?.species ?? []).map((s) => [s.scientific_name, s])), [species]);
  const reach =
    p.src === "trail"
      ? `within ${places?.trail_buffer_m ?? 300} m of the trail`
      : `within ${places?.point_radius_m ?? 500} m`;
  const showOnMap = () => {
    selectPlace({
      id: p.id,
      kind: p.kind,
      name: p.name,
      lon: p.lon,
      lat: p.lat,
      lengthM: p.length_m ?? undefined,
      wiki: p.url ?? null,
      tags: p.tags ?? undefined,
    });
    setPage("map");
  };
  return (
    <article className="page detail">
      <button className="link back" onClick={onBack}>
        <ArrowLeft className="ico" aria-hidden="true" /> All places
      </button>
      <div className="hero">
        {hero ? (
          <figure className="hero-photo">
            <img src={hero.url} alt={`${p.name}, photographed by ${hero.artist}`} />
            <figcaption className="credit">
              <a href={hero.page} target="_blank" rel="noreferrer">
                {hero.artist}
              </a>{" "}
              · {hero.license} · Wikimedia Commons
            </figcaption>
          </figure>
        ) : (
          <div className="hero-photo empty">
            {photos === undefined ? "Looking for a photograph…" : "No licensed photograph nearby"}
          </div>
        )}
        <div className="hero-text">
          <div className="eyebrow">
            {kindLabel(p)}
            {p.ele_m ? ` · ${Math.round(p.ele_m).toLocaleString()} m` : ""}
            {p.length_m ? ` · ${(p.length_m / 1000).toFixed(1)} km` : ""}
          </div>
          <h1>{p.name}</h1>
          <WeatherChip lat={p.lat} lon={p.lon} climate={climate} />
          {summary === undefined ? (
            <p className="muted">Looking up Wikipedia…</p>
          ) : summary ? (
            <p>
              {summary.extract}{" "}
              <a href={summary.url} target="_blank" rel="noreferrer" className="muted small nowrap">
                Wikipedia, CC BY-SA <ExternalLink className="ico" aria-hidden="true" />
              </a>
            </p>
          ) : (
            <p className="muted">No Wikipedia article for this place.</p>
          )}
          <div className="stats">
            <div>
              <strong>{p.near.n.toLocaleString()}</strong>
              <span>sightings {reach}</span>
            </div>
            <div>
              <strong>{p.near.species.toLocaleString()}</strong>
              <span>species recorded here</span>
            </div>
            <div>
              <strong>{b ? MONTHS[b.peak] : <span className="muted">too few</span>}</strong>
              <span>{b ? "busiest month" : "records for a season"}</span>
            </div>
            {p.views_pm != null && (
              <div>
                <strong>{p.views_pm.toLocaleString()}</strong>
                <span>Wikipedia readers a month</span>
              </div>
            )}
          </div>
          {p.tags && (p.tags.fee || p.tags.reservation || p.tags.opening_hours || p.tags.description) && (
            <dl className="facts">
              {p.tags.fee && (
                <>
                  <dt>Fee</dt>
                  <dd>{p.tags.fee}</dd>
                </>
              )}
              {p.tags.reservation && (
                <>
                  <dt>Reservation</dt>
                  <dd>{p.tags.reservation}</dd>
                </>
              )}
              {p.tags.opening_hours && (
                <>
                  <dt>Open</dt>
                  <dd>{p.tags.opening_hours}</dd>
                </>
              )}
              {p.tags.description && (
                <>
                  <dt>Note</dt>
                  <dd>{p.tags.description}</dd>
                </>
              )}
            </dl>
          )}
          <div className="btn-row">
            <button className="primary" onClick={showOnMap}>
              <MapPin className="ico" aria-hidden="true" /> Show on the map
            </button>
            <button
              className="ghost"
              onClick={() => addSite({ id: p.id, label: p.name, lon: p.lon, lat: p.lat, kind: "landmark" })}
            >
              <Plus className="ico" aria-hidden="true" /> Add to a route
            </button>
          </div>
        </div>
      </div>

      <section className="two-col">
        <div>
          <h2>When people go</h2>
          {total > 0 ? (
            <>
              <div className="bars" role="img" aria-label={`Sightings by month: ${p.near.months.join(", ")}`}>
                {p.near.months.map((m, i) => (
                  <div key={i} className="bar-col">
                    <div
                      className={"bar" + (b && i === b.peak ? " peak" : "")}
                      style={{ height: `${(100 * m) / max}%` }}
                      title={`${MONTHS[i]}: ${m}`}
                    />
                    <span className="muted small">{MONTHS[i].slice(0, 1)}</span>
                  </div>
                ))}
              </div>
              <p className="muted small">
                {b ? `${b.label}. ` : ""}Sightings recorded {reach} by month: when people were here and looking, which
                is the best free guide to when to come. Most parks see two thirds of all records in June to August.
              </p>
            </>
          ) : (
            <p className="muted">No sightings recorded {reach} yet, so nothing to say about the season.</p>
          )}
        </div>
        <div>
          <h2>Wildlife seen here</h2>
          {p.near.top.length === 0 ? (
            <p className="muted">Nobody has recorded an animal {reach}.</p>
          ) : (
            <div className="grid tight" role="list">
              {p.near.top.map(([sci, n]) => {
                const s = byName.get(sci);
                const name = s?.common_name ?? sci;
                const photo = speciesPhotos(photosSpecies, sci)[0];
                return (
                  <button key={sci} role="listitem" className="card" onClick={() => selectSpecies(sci)}>
                    <div className="card-media small">
                      {photo ? (
                        <img src={photo.url("small")} alt={name} loading="lazy" />
                      ) : (
                        <div className="card-empty">{name.slice(0, 1)}</div>
                      )}
                    </div>
                    <div className="card-body">
                      <div className="card-title">{name}</div>
                      <div className="small">
                        {n.toLocaleString()} here
                        {photo ? (
                          <span className="muted">
                            {" "}
                            · <PhotoCredit photo={photo} compact />
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          <p className="muted small">
            Counts are what people recorded, not how many animals there are. Sensitive species keep their coarse or
            hidden positions and never appear by place.
          </p>
        </div>
      </section>

      {photos && photos.length > 1 && (
        <section>
          <h2>Photographs nearby</h2>
          <div className="gallery">
            {photos.slice(1).map((ph) => (
              <figure key={ph.url}>
                <a href={ph.page} target="_blank" rel="noreferrer">
                  <img src={ph.url} alt={`${p.name} by ${ph.artist}`} loading="lazy" />
                </a>
                <figcaption className="credit compact">
                  {ph.artist} · {ph.license}
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}
      <p className="muted small">
        Place: OpenStreetMap contributors, ODbL. Readers: Wikimedia pageviews. Photographs: Wikimedia Commons, each
        under the licence shown. Park: {shortPark(parkName)}.
      </p>
    </article>
  );
}
