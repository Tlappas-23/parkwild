// The one place HTML is built from data: MapLibre popups take a string. Every
// value that came from outside (OpenStreetMap names, park names, labels) goes
// through this first, so a name with a tag in it stays text.
export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}
