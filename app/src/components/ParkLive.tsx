import { useEffect, useState } from "react";
import { Activity, Waves } from "lucide-react";
import { fetchGauges, fetchQuakes, QUAKE_DAYS, type BBox, type Gauge, type Quake } from "../lib/usgs";

// What the ground and the rivers are doing right now, from USGS: the month's
// earthquakes inside the park and the nearest gauges' flow and temperature.
// Quiet parks say so; nothing is invented.

// MAX_GAUGES — ARBITRARY (the panel is narrow; three rivers is a reading, ten is a table)
const MAX_GAUGES = 3;
const toF = (c: number) => Math.round((c * 9) / 5 + 32);

export default function ParkLive({ bbox, parkName }: { bbox: BBox; parkName: string }) {
  const [quakes, setQuakes] = useState<Quake[] | null | undefined>(undefined);
  const [gauges, setGauges] = useState<Gauge[] | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setQuakes(undefined);
    setGauges(undefined);
    fetchQuakes(bbox)
      .then((q) => live && setQuakes(q))
      .catch(() => live && setQuakes(null));
    fetchGauges(bbox)
      .then((g) => live && setGauges(g))
      .catch(() => live && setGauges(null));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bbox.join(",")]);
  if (quakes === null && gauges === null) return null;
  const largest = quakes && quakes.length ? quakes.reduce((a, b) => (b.mag > a.mag ? b : a)) : null;
  const shown = (gauges ?? [])
    .slice()
    .sort((a, b) => (b.flowCfs ?? -1) - (a.flowCfs ?? -1))
    .slice(0, MAX_GAUGES);
  return (
    <div className="live" aria-label={`Live readings for ${parkName} from USGS`}>
      <div className="live-row">
        <Waves className="ico" aria-hidden="true" />
        {gauges === undefined ? (
          <span className="muted small">Reading the rivers…</span>
        ) : shown.length === 0 ? (
          <span className="muted small">No USGS stream gauge in this park.</span>
        ) : (
          <div className="live-list">
            {shown.map((g) => (
              <a
                key={g.site}
                href={g.url}
                target="_blank"
                rel="noreferrer"
                className="live-item"
                title={g.time ? `USGS ${g.site}, ${g.time}` : `USGS ${g.site}`}
              >
                <span className="live-name">{g.name}</span>
                <span className="live-val">
                  {g.flowCfs != null && <>{Math.round(g.flowCfs).toLocaleString()} cfs</>}
                  {g.flowCfs != null && g.tempC != null && " · "}
                  {g.tempC != null && <>{toF(g.tempC)}°F water</>}
                </span>
              </a>
            ))}
          </div>
        )}
      </div>
      <div className="live-row">
        <Activity className="ico" aria-hidden="true" />
        {quakes === undefined ? (
          <span className="muted small">Checking the ground…</span>
        ) : quakes === null ? (
          <span className="muted small">Earthquake feed unavailable.</span>
        ) : quakes.length === 0 ? (
          <span className="small">
            No earthquakes of M{QUAKE_MIN_MAG_LABEL}+ in the last {QUAKE_DAYS} days.
          </span>
        ) : (
          <a
            href={largest!.url}
            target="_blank"
            rel="noreferrer"
            className="live-item"
            title={`${largest!.place}, ${largest!.time.slice(0, 10)}`}
          >
            <span className="live-name">
              {quakes.length} earthquake{quakes.length === 1 ? "" : "s"} in {QUAKE_DAYS} days
            </span>
            <span className="live-val">largest M{largest!.mag.toFixed(1)}</span>
          </a>
        )}
      </div>
      <span className="muted small live-credit">USGS, updated as they publish</span>
    </div>
  );
}
const QUAKE_MIN_MAG_LABEL = "1.5";
