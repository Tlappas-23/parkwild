// Every park as a point, for the home page map and the "All parks" view of a
// park's map. Live parks are the accent, configured-but-pending parks are
// hollow, seeded parks are faint dots; the label carries the state.
import type { FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MLMap } from "maplibre-gl";
import type { ParkCard } from "../data/types";

export function parksFC(parks: ParkCard[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: parks
      .filter((p) => p.center)
      .map((p) => ({
        type: "Feature",
        properties: {
          key: p.key,
          name: p.name.replace(/ National Park.*$/, ""),
          state: p.state,
          status: p.status,
          label: `${p.name.replace(/ National Park.*$/, "")}`,
          live: p.status === "live",
        },
        geometry: { type: "Point", coordinates: p.center as [number, number] },
      })),
  };
}

// The bounds that hold every live park; Alaska, Hawaii and the territories
// stretch the seeded set too far to frame by default.
export function liveBounds(parks: ParkCard[]): [[number, number], [number, number]] | null {
  const live = parks.filter((p) => p.status === "live" && p.bbox);
  const pool = live.length ? live : parks.filter((p) => p.bbox);
  if (!pool.length) return null;
  let w = 180,
    e = -180,
    s = 90,
    n = -90;
  for (const p of pool) {
    const [a, b, c, d] = p.bbox!;
    w = Math.min(w, a);
    e = Math.max(e, c);
    s = Math.min(s, b);
    n = Math.max(n, d);
  }
  return [
    [w, s],
    [e, n],
  ];
}

export function addParksLayers(map: MLMap, beforeId?: string): void {
  if (map.getSource("parks")) return;
  map.addSource("parks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer(
    {
      id: "parks-dot",
      type: "circle",
      source: "parks",
      paint: {
        "circle-radius": ["case", ["get", "live"], 8, ["==", ["get", "status"], "planned"], 6, 4],
        "circle-color": ["case", ["get", "live"], "#2563eb", "#ffffff"],
        "circle-stroke-color": ["case", ["get", "live"], "#ffffff", "#475569"],
        "circle-stroke-width": ["case", ["get", "live"], 2, 1.5],
        "circle-opacity": ["case", ["==", ["get", "status"], "seed"], 0.55, 1],
      },
    },
    beforeId,
  );
  map.addLayer(
    {
      id: "parks-label",
      type: "symbol",
      source: "parks",
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["case", ["get", "live"], 12.5, 11],
        "text-offset": [0, 0.9],
        "text-anchor": "top",
        "text-optional": true,
        "text-max-width": 8,
      },
      paint: {
        "text-color": ["case", ["get", "live"], "#12324a", "#4b5563"],
        "text-halo-color": "rgba(255,255,255,0.92)",
        "text-halo-width": 1.3,
        "text-opacity": ["case", ["==", ["get", "status"], "seed"], 0.8, 1],
      },
    },
    beforeId,
  );
}

export function setParksData(map: MLMap, parks: ParkCard[]): void {
  (map.getSource("parks") as GeoJSONSource | undefined)?.setData(parksFC(parks));
}
