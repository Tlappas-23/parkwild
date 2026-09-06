// The park index baked into the build (parkwild/parksindex.py), shared by the
// home page and the park map's "All parks" view.
import type { ParksIndex } from "./types";
export const PARKS_INDEX: ParksIndex = Object.values(import.meta.glob<ParksIndex>("../public/data/parks.json", { eager: true, import: "default" }))[0]
  ?? { generated: "", attribution: "", parks: [] };
