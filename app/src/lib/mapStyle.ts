// The map's palette in one place, so the drawn map, the overlays and the
// site share a look. The base is OpenFreeMap's dark style (OpenStreetMap
// data, ODbL), with its background set to the site's own ground so the map
// and the page are one surface. Everything drawn on top uses these inks.
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/dark";
export const MAP_GROUND = "#0f1412";
export const INK = "#ede9df"; // light text and lines on the dark map
export const INK_HALO = "rgba(15, 20, 18, 0.85)";
export const ACCENT = "#7aa2ff"; // the site's one accent: route, stops, the visitor
export const ACCENT_DEEP = "#3b6fe0";
export const PARK_LINE = "#8fd3a5"; // the park boundary
export const PLACE = "#a9b3bd"; // things to do, landmarks that are not stops
export const WARM = "#f0c37a"; // labels of things to do
export const CORRIDOR = "#e0a24a"; // the camera pass, the model colour
export const MASK = "#0a1016"; // the wash over everything outside the park
export const HILLSHADE = { shadow: "#000000", highlight: "#9fb2a6", accent: "#1c2620", exaggeration: 0.4 };
