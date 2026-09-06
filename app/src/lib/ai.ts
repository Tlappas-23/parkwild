// "Ask the park": a small language model that runs in the visitor's browser
// over WebGPU and answers only from this park's own data.
//
// Nothing here calls a hosted model. The model is downloaded once from
// Hugging Face into the browser's cache (about a gigabyte), the question and
// the facts never leave the device, and the answer must cite the facts it
// used. Retrieval is deliberately simple: names in the question select
// species and places; intent words select what to add (months, camping,
// trails, a plan). The model's job is to write, not to know (ADR-0021).
import type { MLCEngine } from "@mlc-ai/web-llm";
import { fmtKm, fmtTime, planRoute, routerFor, type Site } from "./routing";
import { useStore } from "../store/index";
import { fmtDist, haversineM, nearbySpecies, thingsNear, tourStops } from "./tour";
import type { Landmark, Species } from "../data/types";

// MODEL_ID — BORROWED (Qwen2.5 1.5B Instruct, Apache-2.0, 4-bit; the smallest
// model that follows a "cite your facts" instruction reliably in testing;
// about 1 GB to download, about 1.6 GB of GPU memory)
export const DEFAULT_MODEL_ID = "Qwen2.5-1.5B-Instruct-q4f16_1-MLC";
// A smaller model can be forced for testing on machines or profiles that
// cannot hold the default (localStorage "parkwild:ai-model"); the answer view
// always names the model that produced it.
function modelOverride(): string | null {
  try {
    return localStorage.getItem("parkwild:ai-model");
  } catch {
    return null;
  }
}
export const MODEL_ID = modelOverride() || DEFAULT_MODEL_ID;
// MAX_FACTS — ARBITRARY (a 1.5B model loses the thread past a page of context)
export const MAX_FACTS = 28;
// GEN — ARBITRARY (low temperature for a writer that must not improvise; enough tokens for six sentences)
export const GEN = { temperature: 0.2, top_p: 0.9, max_tokens: 320 };

export const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function webgpuAvailable(): boolean {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

let engine: MLCEngine | null = null;
let loading: Promise<MLCEngine> | null = null;
export function engineReady(): boolean {
  return engine !== null;
}

export function loadEngine(onProgress: (text: string, pct: number) => void): Promise<MLCEngine> {
  if (engine) return Promise.resolve(engine);
  if (!loading) {
    loading = import("@mlc-ai/web-llm")
      .then(async (webllm) => {
        const opts = {
          initProgressCallback: (r: { text: string; progress: number }) => onProgress(r.text, r.progress),
        };
        // Some browsers refuse large Cache API writes while still reporting free
        // quota; the weights then go through the origin's private file system,
        // and failing that IndexedDB. Each backend keeps its own copy.
        let e: MLCEngine | null = null;
        let lastErr: unknown = null;
        for (const cacheBackend of ["cache", "opfs", "indexeddb"] as const) {
          try {
            e = await webllm.CreateMLCEngine(MODEL_ID, {
              ...opts,
              appConfig: { ...webllm.prebuiltAppConfig, cacheBackend },
            });
            break;
          } catch (err) {
            lastErr = err;
            if (!/quota/i.test(String(err))) throw err;
            onProgress(
              `${cacheBackend === "cache" ? "Cache storage" : cacheBackend === "opfs" ? "The private file system" : "IndexedDB"} refused the download; trying another store…`,
              0,
            );
          }
        }
        if (!e) throw lastErr;
        engine = e;
        return e;
      })
      .catch((err) => {
        loading = null;
        throw err;
      });
  }
  return loading;
}

export interface Fact {
  n: number;
  text: string;
  href?: string;
  label?: string;
}
export interface Grounding {
  facts: Fact[];
  species: Species[];
  places: Landmark[];
  intents: string[];
  month: number | null;
}

function norm(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// GENERIC — ASSUMED (words in common names that do not pick a species on their own)
const GENERIC = new Set([
  "american",
  "common",
  "northern",
  "western",
  "eastern",
  "southern",
  "great",
  "greater",
  "lesser",
  "little",
  "mountain",
  "rocky",
  "north",
  "canada",
  "canadian",
  "grey",
  "gray",
  "red",
  "white",
  "black",
  "brown",
  "yellow",
  "blue",
  "golden",
  "ground",
  "tree",
  "rock",
  "sage",
  "spotted",
  "striped",
  "long",
  "short",
  "tailed",
  "eared",
  "headed",
  "billed",
  "winged",
  "the",
  "of",
  "and",
]);

function singular(w: string): string {
  if (w === "wolves") return "wolf";
  if (w === "geese") return "goose";
  if (w === "mice") return "mouse";
  if (w.endsWith("ies") && w.length > 4) return w.slice(0, -3) + "y";
  if (w.endsWith("es") && /(sh|ch|x|s)es$/.test(w)) return w.slice(0, -2);
  return w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w;
}

// Which species a question names. A whole name wins ("golden-mantled ground
// squirrel"); otherwise its distinctive words ("bison" in "American Bison",
// "elk" among Wapiti's other names); a bare generic word ("bear") is ambiguous
// and picks nothing unless only one species carries it. Sorted by how much
// of the name matched, then by how often the species is seen.
export function matchSpecies(q: string, all: Species[]): Species[] {
  const qWords = new Set(q.split(" ").flatMap((w) => [w, singular(w)]));
  const scored: { s: Species; score: number }[] = [];
  for (const s of all) {
    if (s.suppression?.action === "exclude") continue;
    let best = 0;
    for (const n of [s.common_name ?? "", ...(s.other_names ?? []), s.scientific_name]) {
      const nn = norm(n);
      if (!nn) continue;
      if (q.includes(nn) || q.includes(nn + "s")) {
        best = Math.max(best, 3);
        continue;
      }
      const words = nn.split(" ");
      const distinctive = words.filter((w) => !GENERIC.has(w));
      if (distinctive.length && distinctive.every((w) => qWords.has(w)))
        best = Math.max(best, distinctive.length === words.length ? 2.5 : 2);
    }
    if (best) scored.push({ s, score: best });
  }
  // A generic last word alone ("bear", "squirrel") counts only when it is unambiguous.
  if (scored.length === 0) {
    const byWord = new Map<string, Species[]>();
    for (const s of all) {
      if (s.suppression?.action === "exclude" || !s.common_name) continue;
      const last = norm(s.common_name).split(" ").pop() ?? "";
      if (qWords.has(last)) byWord.set(last, [...(byWord.get(last) ?? []), s]);
    }
    for (const list of byWord.values()) if (list.length === 1) scored.push({ s: list[0], score: 1 });
  }
  return scored
    .sort((a, b) => b.score - a.score || b.s.sightings - a.s.sightings)
    .slice(0, 3)
    .map((x) => x.s);
}

// What the question is about, from names and a few intent words. No model here.
export function ground(question: string): Grounding {
  const st = useStore.getState();
  const q = norm(question);
  const words = new Set(q.split(" "));
  const facts: Fact[] = [];
  const add = (text: string, href?: string, label?: string) => {
    if (facts.length < MAX_FACTS) facts.push({ n: facts.length + 1, text, href, label });
  };
  const intents: string[] = [];
  for (const [k, re] of Object.entries({
    plan: /\b(plan|itinerary|day|hours?|route|trip|visit)\b/,
    camp: /\b(camp|campground|campsite|tent|rv|sleep|stay|lodge|hotel|cabin)\b/,
    hike: /\b(hike|hiking|trail|walk|walking)\b/,
    when: /\b(when|month|season|time of year|best time)\b/,
    where: /\b(where|see|find|spot|spots|most|likely)\b/,
    model: /\b(model|camera|ai|computer vision|detection|detect)\b/,
    photo: /\b(photo|picture|image)\b/,
    count: /\b(how many|number|count|total)\b/,
  }))
    if (re.test(q)) intents.push(k);
  const month = MONTHS.findIndex((m) => q.includes(m.toLowerCase()) || words.has(m.slice(0, 3).toLowerCase()));

  const all = st.species?.species ?? [];
  const species = matchSpecies(q, all);
  const landmarks = st.landmarks?.landmarks ?? [];
  const places = landmarks
    .filter((l) => {
      const nn = norm(l.name);
      return nn && q.includes(nn);
    })
    .slice(0, 3);
  const stops = tourStops(st.landmarks);

  // Park-level facts, always present.
  const total = all.reduce((a, s) => a + s.sightings, 0);
  const effort = new Array<number>(12).fill(0);
  for (const s of all)
    s.months.forEach((m, i) => {
      effort[i] += m;
    });
  const eTotal = effort.reduce((a, b) => a + b, 0) || 1;
  add(
    `${st.parkName}: ${total.toLocaleString()} recorded sightings of ${all.length} species from iNaturalist research-grade observations and GBIF datasets; ${Math.round((100 * (effort[5] + effort[6] + effort[7])) / eTotal)}% of all sightings fall in June to August because that is when people visit.`,
    undefined,
    "Park summary",
  );
  if (stops.length)
    add(
      `The park's tour has ${stops.length} stops in order: ${stops.map((s) => s.name).join(", ")}.`,
      undefined,
      "Tour",
    );
  const cp = st.cameraPass;
  if (cp) {
    const ran = cp.corridors.filter((c) => c.status !== "planned");
    add(
      ran.length
        ? `Roadside camera pass (computer vision on street-level photos): ${ran.map((c) => `${c.name.split(",")[0]}: ${c.frames_scored.toLocaleString()} frames scored, ${c.sightings} model sightings, ${c.named} named to species${c.precision?.precision !== null && c.precision ? `, measured precision ${Math.round(100 * c.precision.precision)}%` : ""}`).join("; ")}. Model counts are tiny next to human sightings and are shown separately.`
        : `The roadside camera pass has not run in ${st.parkName} yet; every count on the site is from people.`,
      undefined,
      "Camera pass",
    );
  }

  const relPeak = (s: Species) => {
    const t = s.months.reduce((a, b) => a + b, 0);
    if (t < 30) return null;
    const rel = s.months.map((m, i) => (effort[i] ? m / t / (effort[i] / eTotal) : 0));
    const i = rel.indexOf(Math.max(...rel));
    return { month: MONTHS[i], ratio: rel[i] };
  };
  for (const s of species) {
    const name = s.common_name ?? s.scientific_name;
    const busiest = MONTHS[s.months.indexOf(Math.max(...s.months))];
    const rp = relPeak(s);
    add(
      `${name} (${s.scientific_name}): ${s.sightings.toLocaleString()} sightings, ${s.confidence_basis.human_verified.toLocaleString()} verified by people and ${s.confidence_basis.model_predicted} model-predicted, recorded ${s.first?.slice(0, 4)} to ${s.last?.slice(0, 4)}; busiest month ${busiest}${rp ? `; seen ${rp.ratio.toFixed(1)}× more than usual in ${rp.month}` : ""}${s.suppression ? `; mapped coarsely (${s.suppression.why})` : ""}.`,
      `#species/${s.scientific_name}`,
      name,
    );
    // Where: the busiest cells for the species, named by the nearest landmark.
    const cells = st.cells;
    if (cells && !s.suppression) {
      const idx = cells.species_index.findIndex((e) => e.n === s.scientific_name);
      const top = cells.features
        .filter((f) => !f.properties.coarsened)
        .map((f) => ({ f, e: f.properties.sp.find((x) => x[0] === idx) }))
        .filter((x): x is { f: typeof x.f; e: NonNullable<typeof x.e> } => !!x.e)
        .sort((a, b) => b.e[1] - a.e[1])
        .slice(0, 3);
      const named = top.map(({ f, e }) => {
        const ring = f.geometry.coordinates[0];
        let cx = 0,
          cy = 0;
        for (let i = 0; i < ring.length - 1; i++) {
          cx += ring[i][0];
          cy += ring[i][1];
        }
        cx /= ring.length - 1;
        cy /= ring.length - 1;
        let best: Landmark | null = null,
          bd = Infinity;
        for (const l of landmarks) {
          const d = haversineM(cx, cy, l.lon, l.lat);
          if (d < bd) {
            bd = d;
            best = l;
          }
        }
        return `${e[1]} near ${best ? `${best.name} (${fmtDist(bd)} away)` : "an unnamed spot"}`;
      });
      if (named.length)
        add(
          `Where ${name} is recorded most, by 170 m cell: ${named.join("; ")}.`,
          `#map/${s.scientific_name}`,
          `${name} on the map`,
        );
    }
  }

  for (const l of places) {
    const near = nearbySpecies(st.cells, l.lon, l.lat);
    add(
      `${l.name} (${l.kind}${l.ele_m ? `, ${Math.round(l.ele_m)} m` : ""})${l.summary?.extract ? `: ${l.summary.extract.slice(0, 260)}` : ""}`,
      l.summary?.url ?? l.url ?? undefined,
      l.name,
    );
    if (near.list.length)
      add(
        `Recorded within 2.5 km of ${l.name}: ${near.list.map((n) => `${n.common ?? n.species} ${n.count}`).join(", ")} (${near.total.toLocaleString()} sightings in ${near.cells} cells).`,
        undefined,
        `Around ${l.name}`,
      );
    const th = thingsNear(st.amenities, l.lon, l.lat);
    if (intents.includes("hike") && (th.trails.length || th.hike.length))
      add(
        `Trails near ${l.name}: ${[...th.trails, ...th.hike]
          .slice(0, 5)
          .map((t) => `${t.label} (${t.detail})`)
          .join("; ")}.`,
        undefined,
        `Trails near ${l.name}`,
      );
    if (intents.includes("camp") && (th.camp.length || th.stay.length))
      add(
        `Camping and lodging near ${l.name}: ${[...th.camp, ...th.stay]
          .slice(0, 5)
          .map((t) => `${t.label} (${t.detail})`)
          .join("; ")}.`,
        undefined,
        `Camping near ${l.name}`,
      );
  }

  if (month >= 0) {
    const ranked = all
      .filter((s) => s.months.reduce((a, b) => a + b, 0) >= 30 && !s.suppression)
      .map((s) => {
        const t = s.months.reduce((a, b) => a + b, 0);
        return { s, r: s.months[month] / t / (effort[month] / eTotal), n: s.months[month] };
      })
      .filter((x) => x.n >= 10)
      .sort((a, b) => b.r - a.r)
      .slice(0, 6);
    if (ranked.length)
      add(
        `Species seen more than usual in ${MONTHS[month]} (share of their sightings vs everyone's): ${ranked.map((x) => `${x.s.common_name ?? x.s.scientific_name} ${x.r.toFixed(1)}× (${x.n} in ${MONTHS[month]})`).join(", ")}.`,
        undefined,
        `${MONTHS[month]}`,
      );
  }
  if (intents.includes("camp") && places.length === 0 && st.amenities) {
    const camps = st.amenities.items
      .filter((i) => i.kind === "camp" && i.named && i.tags.backcountry !== "yes")
      .slice(0, 8);
    if (camps.length)
      add(
        `Named campgrounds in the data: ${camps.map((c) => `${c.name}${c.tags.capacity ? ` (${c.tags.capacity} sites)` : ""}${c.tags.reservation ? `, reservation ${c.tags.reservation}` : ""}`).join("; ")}. Fees, seasons and reservations as tagged in OpenStreetMap; check nps.gov.`,
        undefined,
        "Campgrounds",
      );
  }
  if (intents.includes("hike") && places.length === 0 && st.amenities) {
    const trails = st.amenities.trails.slice(0, 8);
    if (trails.length)
      add(
        `Longest named trails: ${trails.map((t) => `${t.name} ${(t.length_m / 1000).toFixed(1)} km`).join(", ")}.`,
        undefined,
        "Trails",
      );
  }
  return { facts, species, places, intents, month: month >= 0 ? month : null };
}

// A day plan, computed, never imagined: start at a named place (or the first
// stop), visit the busiest spots of the species asked for and the places
// named, ordered by the route planner over the park's roads.
export async function planFacts(g: Grounding): Promise<Fact[]> {
  const st = useStore.getState();
  await st.ensureRoads();
  const roads = useStore.getState().roads;
  const stops = tourStops(st.landmarks);
  const start = g.places[0] ?? stops[0];
  if (!roads || !start || !st.cells) return [];
  const sites: Site[] = [];
  for (const s of g.species) {
    const idx = st.cells.species_index.findIndex((e) => e.n === s.scientific_name);
    const top = st.cells.features
      .filter((f) => !f.properties.coarsened)
      .map((f) => ({ f, e: f.properties.sp.find((x) => x[0] === idx) }))
      .filter((x): x is { f: typeof x.f; e: NonNullable<typeof x.e> } => !!x.e)
      .sort((a, b) => b.e[1] - a.e[1])
      .slice(0, 2);
    for (const { f, e } of top) {
      const ring = f.geometry.coordinates[0];
      let cx = 0,
        cy = 0;
      for (let i = 0; i < ring.length - 1; i++) {
        cx += ring[i][0];
        cy += ring[i][1];
      }
      cx /= ring.length - 1;
      cy /= ring.length - 1;
      sites.push({
        id: `cell:${f.properties.cell}`,
        label: `${s.common_name ?? s.scientific_name} spot (${e[1]} sightings)`,
        lon: cx,
        lat: cy,
        kind: "cell",
      });
    }
  }
  for (const p of g.places.slice(1)) sites.push({ id: p.id, label: p.name, lon: p.lon, lat: p.lat, kind: "landmark" });
  if (sites.length === 0)
    for (const s of stops.slice(1, 5)) sites.push({ id: s.id, label: s.name, lon: s.lon, lat: s.lat, kind: "stop" });
  const startSite: Site = { id: start.id, label: start.name, lon: start.lon, lat: start.lat, kind: "stop" };
  const plan = planRoute(routerFor(roads), startSite, sites.slice(0, 8), "drive");
  const legs = plan.legs.map(
    (l, i) => `${i + 1}. ${l.to.label}: ${fmtKm(l.distanceM)}, about ${fmtTime(l.seconds)} from ${l.from.label}`,
  );
  return [
    {
      n: 0,
      text: `A driving plan from ${start.name} over the park's roads (shortest order, ${fmtKm(plan.distanceM)} and about ${fmtTime(plan.seconds)} in total, assuming 35 mph and five minutes a stop): ${legs.join("; ")}.${plan.unreachable.length ? ` Not on the road network: ${plan.unreachable.map((u) => u.label).join(", ")}.` : ""}`,
      label: "Plan",
    },
  ];
}

export interface Answer {
  text: string;
  facts: Fact[];
  cited: number[];
  uncited_numbers: string[];
  ms: number;
  grounding: Grounding;
}

const SYSTEM = (park: string) =>
  `You are the guide for parkwild, a map of wildlife sightings in ${park}. Answer using ONLY the numbered FACTS. Every sentence must rest on a fact, and you cite it with its number in square brackets, like [2]. Never add species, places, numbers, dates or history that are not in the facts. If the facts do not answer the question, say "The data doesn't say" and name what the facts do cover. Write plainly in 3 to 6 short sentences, no headings, no bullet points, no preamble.`;

export async function ask(question: string, onToken?: (partial: string) => void): Promise<Answer> {
  const t0 = performance.now();
  const g = ground(question);
  if (g.intents.includes("plan")) {
    for (const f of await planFacts(g)) {
      f.n = g.facts.length + 1;
      g.facts.push(f);
    }
  }
  const e = await loadEngine(() => undefined);
  const factText = g.facts.map((f) => `[${f.n}] ${f.text}`).join("\n");
  const messages = [
    { role: "system" as const, content: SYSTEM(useStore.getState().parkName) },
    { role: "user" as const, content: `FACTS:\n${factText}\n\nQUESTION: ${question}` },
  ];
  let text = "";
  const stream = await e.chat.completions.create({ messages, stream: true, ...GEN });
  for await (const chunk of stream) {
    text += chunk.choices[0]?.delta?.content ?? "";
    onToken?.(text);
  }
  text = text.trim();
  const cited = [...new Set([...text.matchAll(/\[(\d+)\]/g)].map((m) => +m[1]))].filter((n) =>
    g.facts.some((f) => f.n === n),
  );
  // Numbers the model wrote that appear in no fact: the honesty check the eval reads.
  const clean = (n: string) => n.replace(/[.,]+$/, "");
  const factNums = new Set((factText.match(/\d[\d,\.]*/g) ?? []).map(clean));
  // Numbers of three or more digits that no fact contains; list numerals and
  // citation markers are not numbers the model asserted.
  const uncited_numbers = [...new Set((text.replace(/\[\d+\]/g, "").match(/\d[\d,\.]*/g) ?? []).map(clean))].filter(
    (n) => !factNums.has(n) && n.replace(/[^\d]/g, "").length >= 3,
  );
  return { text, facts: g.facts, cited, uncited_numbers, ms: Math.round(performance.now() - t0), grounding: g };
}

// EVAL_QUESTIONS — the measured set (docs/ai-eval.md): what a visitor asks,
// and what a grounded answer must cite. Run from the console:
// window.__parkwildAsk.evaluate().
export const EVAL_QUESTIONS = [
  "Where are bison seen most?",
  "When is the best month to see elk?",
  "How many species have been recorded here?",
  "Where can I camp near Lamar Valley?",
  "What trails are near Old Faithful?",
  "Plan a half day from Old Faithful to see bison and elk",
  "What animals are seen around Hayden Valley?",
  "Which birds are seen more than usual in October?",
  "How good is the camera model?",
  "Are there wolves on the map?",
  "What is the tallest peak?",
  "Tell me about Mammoth Hot Springs",
];

export async function evaluate(questions = EVAL_QUESTIONS): Promise<
  {
    question: string;
    cited: number;
    facts: number;
    uncited_numbers: string[];
    says_no_data: boolean;
    ms: number;
    text: string;
  }[]
> {
  const out = [];
  for (const q of questions) {
    const a = await ask(q);
    out.push({
      question: q,
      cited: a.cited.length,
      facts: a.facts.length,
      uncited_numbers: a.uncited_numbers,
      says_no_data: /doesn't say|does not say/i.test(a.text),
      ms: a.ms,
      text: a.text,
    });
  }
  return out;
}

if (typeof window !== "undefined")
  (window as unknown as { __parkwildAsk?: unknown }).__parkwildAsk = { ask, ground, evaluate, MODEL_ID };
