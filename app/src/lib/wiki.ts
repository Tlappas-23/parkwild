// Runtime lookups for the place drawer: a summary from Wikipedia and licensed
// photographs from Wikimedia Commons. Both endpoints are free, keyless and
// answer cross-origin; only a title or a coordinate leaves the browser, and
// answers are cached for the session. The licence rule is the pipeline's
// (ADR-0019): public domain, CC0, CC BY, CC BY-SA; nothing else is shown.
const cache = new Map<string, Promise<unknown>>();
function once<T>(key: string, fn: () => Promise<T>): Promise<T> {
  if (!cache.has(key))
    cache.set(
      key,
      fn().catch((e) => {
        cache.delete(key);
        throw e;
      }),
    );
  return cache.get(key) as Promise<T>;
}

export interface Summary {
  title: string;
  extract: string;
  url: string;
}
export interface CommonsPhoto {
  url: string;
  page: string;
  artist: string;
  license: string;
  distM: number;
}

// REUSABLE — BORROWED (Commons' LicenseShortName prefixes that allow reuse with credit)
const REUSABLE = ["public domain", "pd", "cc0", "cc by"];
// PHOTO_RADIUS_M — ASSUMED (a photograph within this shows the place; boardwalks and overlooks sit a few hundred metres off)
export const PHOTO_RADIUS_M = 400;

// The browser's own parser turns the API's HTML into text; a regex that
// strips tags can leave "<script" behind after one pass (CodeQL js/incomplete-multi-character-sanitization).
function text(html: string | undefined): string {
  const doc = new DOMParser().parseFromString(html ?? "", "text/html");
  return (doc.body.textContent ?? "").replace(/\s+/g, " ").trim();
}

export function wikiSummary(title: string): Promise<Summary | null> {
  return once(`s:${title}`, async () => {
    const r = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title.replace(/ /g, "_"))}`,
      { headers: { accept: "application/json" } },
    );
    if (!r.ok) return null;
    const j = (await r.json()) as {
      type?: string;
      title?: string;
      extract?: string;
      content_urls?: { desktop?: { page?: string } };
    };
    if (j.type === "disambiguation" || !j.extract) return null;
    return {
      title: j.title ?? title,
      extract: j.extract,
      url: j.content_urls?.desktop?.page ?? `https://en.wikipedia.org/wiki/${encodeURIComponent(title)}`,
    };
  });
}

// For a place with no article link: search, and accept the top hit only if
// its title carries the place's own name, so "Fairy Falls Trail" may land on
// "Fairy Falls (Wyoming)" but "Campsite" never lands on anything.
export function wikiFind(name: string, park: string): Promise<Summary | null> {
  return once(`f:${name}|${park}`, async () => {
    const stem = name
      .replace(/\b(trail|trailhead|campground|campsite|picnic area|overlook|viewpoint|visitor center)\b/gi, "")
      .trim();
    if (stem.split(/\s+/).filter(Boolean).length === 0 || /^\d/.test(stem)) return null;
    const u = `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(`"${stem}" ${park}`)}&srlimit=3&format=json&origin=*`;
    const r = await fetch(u);
    if (!r.ok) return null;
    const j = (await r.json()) as { query?: { search?: { title: string }[] } };
    const key = stem.toLowerCase();
    const hit = (j.query?.search ?? []).find((h) => h.title.toLowerCase().includes(key));
    return hit ? wikiSummary(hit.title) : null;
  });
}

export function commonsNear(lat: number, lon: number, radiusM = PHOTO_RADIUS_M, limit = 6): Promise<CommonsPhoto[]> {
  return once(`c:${lat.toFixed(4)},${lon.toFixed(4)},${radiusM}`, async () => {
    const api = "https://commons.wikimedia.org/w/api.php";
    const g = await fetch(
      `${api}?action=query&list=geosearch&gscoord=${lat}%7C${lon}&gsradius=${radiusM}&gsnamespace=6&gslimit=16&format=json&origin=*`,
    );
    if (!g.ok) return [];
    const gj = (await g.json()) as { query?: { geosearch?: { title: string; dist: number }[] } };
    const hits = (gj.query?.geosearch ?? []).filter((h) => /\.(jpe?g|png)$/i.test(h.title));
    if (!hits.length) return [];
    const q = await fetch(
      `${api}?action=query&titles=${encodeURIComponent(hits.map((h) => h.title).join("|"))}&prop=imageinfo&iiprop=extmetadata%7Curl&iiurlwidth=640&format=json&origin=*`,
    );
    if (!q.ok) return [];
    const qj = (await q.json()) as {
      query?: {
        pages?: Record<
          string,
          {
            title: string;
            imageinfo?: {
              thumburl?: string;
              descriptionurl?: string;
              extmetadata?: Record<string, { value: string }>;
            }[];
          }
        >;
      };
    };
    const pages = new Map(Object.values(qj.query?.pages ?? {}).map((p) => [p.title, p]));
    const out: CommonsPhoto[] = [];
    for (const h of hits) {
      const info = pages.get(h.title)?.imageinfo?.[0];
      const em = info?.extmetadata ?? {};
      const license = text(em.LicenseShortName?.value);
      if (!info?.thumburl || !REUSABLE.some((p) => license.toLowerCase().startsWith(p))) continue;
      const artist = text(em.Artist?.value) || "unknown";
      out.push({
        url: info.thumburl.replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/").split("?")[0],
        page: info.descriptionurl ?? "",
        artist: artist.length > 60 ? artist.slice(0, 59) + "…" : artist,
        license,
        distM: Math.round(h.dist),
      });
      if (out.length >= limit) break;
    }
    return out;
  });
}
