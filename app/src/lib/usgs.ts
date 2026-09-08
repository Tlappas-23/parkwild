// Live readings from the US Geological Survey, free and keyless, fetched by
// the browser when a park is open: the last month of earthquakes inside the
// park's box (the Earthquake Hazards Program feed), the nearest stream
// gauges with their current flow and water temperature (the National Water
// Information System), and an elevation for a place that has none in
// OpenStreetMap (the Elevation Point Query Service, a point read of the 3DEP
// model). Nothing is stored; a short cache keeps a tour from asking twice.
export interface Quake {
  mag: number;
  place: string;
  time: string;
  depthKm: number;
  lon: number;
  lat: number;
  url: string;
}
export interface Gauge {
  site: string;
  name: string;
  lon: number;
  lat: number;
  flowCfs: number | null;
  tempC: number | null;
  time: string | null;
  url: string;
}

// QUAKE_URL / WATER_URL — BORROWED (USGS FDSN event service; USGS NWIS instantaneous values)
const QUAKE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query";
const WATER_URL = "https://waterservices.usgs.gov/nwis/iv/";
// ELEVATION_URL — BORROWED (USGS Elevation Point Query Service, a point read of the 3DEP elevation model)
const ELEVATION_URL = "https://epqs.nationalmap.gov/v1/json";
// ELEVATION_FLOOR_M — BORROWED (EPQS marks no data with -1,000,000; the lowest ground in any park is Badwater at -86 m)
export const ELEVATION_FLOOR_M = -500;
// QUAKE_DAYS — ARBITRARY (a month is long enough to say "active" or "quiet" about a park)
export const QUAKE_DAYS = 30;
// QUAKE_MIN_MAG — BORROWED (below about 1.5 the catalogue is incomplete outside dense networks)
export const QUAKE_MIN_MAG = 1.5;
// CACHE_MS — ARBITRARY (both feeds update on the order of minutes; ten is plenty for a visit)
const CACHE_MS = 10 * 60 * 1000;
const cache = new Map<string, { at: number; v: unknown }>();

async function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.v as T;
  const v = await load();
  cache.set(key, { at: Date.now(), v });
  return v;
}

export type BBox = [number, number, number, number]; // west, south, east, north

export function fetchQuakes(bbox: BBox, today: Date = new Date()): Promise<Quake[]> {
  const [w, s, e, n] = bbox;
  const start = new Date(today.getTime() - QUAKE_DAYS * 86_400_000).toISOString().slice(0, 10);
  const url =
    `${QUAKE_URL}?format=geojson&starttime=${start}&minlatitude=${s}&maxlatitude=${n}` +
    `&minlongitude=${w}&maxlongitude=${e}&minmagnitude=${QUAKE_MIN_MAG}&orderby=time`;
  return cached(`q:${bbox.join(",")}`, async () => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`quakes: HTTP ${res.status}`);
    const j = (await res.json()) as {
      features: {
        properties: { mag: number; place: string; time: number; url: string };
        geometry: { coordinates: [number, number, number] };
      }[];
    };
    return j.features.map((f) => ({
      mag: f.properties.mag,
      place: f.properties.place,
      time: new Date(f.properties.time).toISOString(),
      depthKm: f.geometry.coordinates[2],
      lon: f.geometry.coordinates[0],
      lat: f.geometry.coordinates[1],
      url: f.properties.url,
    }));
  });
}

export function fetchGauges(bbox: BBox): Promise<Gauge[]> {
  const [w, s, e, n] = bbox;
  const box = [w, s, e, n].map((v) => v.toFixed(3)).join(",");
  const url = `${WATER_URL}?format=json&bBox=${box}&parameterCd=00060,00010&siteStatus=active`;
  return cached(`g:${box}`, async () => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`gauges: HTTP ${res.status}`);
    const j = (await res.json()) as {
      value: {
        timeSeries: {
          sourceInfo: {
            siteName: string;
            siteCode: { value: string }[];
            geoLocation: { geogLocation: { latitude: number; longitude: number } };
          };
          variable: { variableCode: { value: string }[] };
          values: { value: { value: string; dateTime: string }[] }[];
        }[];
      };
    };
    const bySite = new Map<string, Gauge>();
    for (const t of j.value.timeSeries) {
      const site = t.sourceInfo.siteCode[0]?.value ?? t.sourceInfo.siteName;
      const g =
        bySite.get(site) ??
        ({
          site,
          name: titleCase(t.sourceInfo.siteName),
          lon: t.sourceInfo.geoLocation.geogLocation.longitude,
          lat: t.sourceInfo.geoLocation.geogLocation.latitude,
          flowCfs: null,
          tempC: null,
          time: null,
          url: `https://waterdata.usgs.gov/monitoring-location/${site}/`,
        } as Gauge);
      const last = t.values[0]?.value.at(-1);
      if (last) {
        const v = Number(last.value);
        const code = t.variable.variableCode[0]?.value;
        if (code === "00060" && v > -999) g.flowCfs = v;
        if (code === "00010" && v > -999) g.tempC = v;
        g.time = last.dateTime;
      }
      bySite.set(site, g);
    }
    return [...bySite.values()].filter((g) => g.flowCfs != null || g.tempC != null);
  });
}

// The service answers HTTP 200 with the text "Call failed." for a point off
// its raster and a value of -1,000,000 for no data, so the body is read as
// text and anything that is not a finite number above the floor counts as no
// elevation. Pure, so it can be tested against captured bodies.
export function parseElevation(body: string): number | null {
  let j: unknown;
  try {
    j = JSON.parse(body);
  } catch {
    return null;
  }
  const raw = (j as { value?: unknown } | null)?.value;
  if (raw == null) return null;
  const v = Number(raw);
  return Number.isFinite(v) && v >= ELEVATION_FLOOR_M ? v : null;
}

export function fetchElevation(lon: number, lat: number): Promise<number | null> {
  // Four decimals is about 11 m, the precision the weather request uses; the rounded pair also keys the cache.
  const x = lon.toFixed(4);
  const y = lat.toFixed(4);
  return cached(`e:${x},${y}`, async () => {
    const res = await fetch(`${ELEVATION_URL}?x=${x}&y=${y}&units=Meters`);
    if (!res.ok) throw new Error(`elevation: HTTP ${res.status}`);
    return parseElevation(await res.text());
  });
}

// "NORTH FORK VIRGIN RIVER NEAR SPRINGDALE, UT" reads better in title case, with the small words kept small.
function titleCase(s: string): string {
  const small = new Set(["at", "near", "of", "the", "and", "nr", "blw", "abv"]);
  return s
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) => (i > 0 && small.has(w) ? w : w.replace(/^[a-z]/, (c) => c.toUpperCase())))
    .join(" ")
    .replace(/, ([a-z]{2})$/i, (_, st: string) => `, ${st.toUpperCase()}`);
}
