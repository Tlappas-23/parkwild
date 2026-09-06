import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { addParksLayers, liveBounds, setParksData } from "../parksOverlay";
import { useStore } from "../store";
import type { ParkCard } from "../types";

// The country with every park on it. A live park opens on click; the rest
// say what they are. Same style and fonts as the park map, no terrain: this
// is a picker, not a place.
const STYLE = "https://tiles.openfreemap.org/styles/liberty";

export default function HomeMap({ parks }: { parks: ParkCard[] }) {
  const container = useRef<HTMLDivElement>(null);
  const { enterPark, reducedMotion } = useStore();
  const enterRef = useRef(enterPark); enterRef.current = enterPark;

  useEffect(() => {
    if (!container.current) return;
    const b = liveBounds(parks);
    const map = new maplibregl.Map({ container: container.current, style: STYLE, center: [-98, 39], zoom: 3, attributionControl: { compact: true }, fadeDuration: reducedMotion ? 0 : 300 });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => {
      addParksLayers(map);
      setParksData(map, parks);
      if (b) map.fitBounds(b, { padding: 60, duration: 0, maxZoom: 6 });
      map.on("click", "parks-dot", (e) => {
        const f = e.features?.[0]; if (!f) return;
        const p = f.properties as { key: string; live: boolean; name: string; status: string };
        if (p.live) { enterRef.current(p.key); return; }
        new maplibregl.Popup({ closeButton: false, offset: 10 }).setLngLat(e.lngLat)
          .setHTML(`<strong>${p.name}</strong><br><span class="muted">${p.status === "planned" ? "sightings are being gathered" : "not started yet"}</span>`).addTo(map);
      });
      map.on("mouseenter", "parks-dot", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "parks-dot", () => (map.getCanvas().style.cursor = ""));
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);
    return () => { ro.disconnect(); map.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={container} className="home-map" role="region" aria-label="Map of every park" />;
}
