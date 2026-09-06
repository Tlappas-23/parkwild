import { useEffect, useState } from "react";
import type { ClimateFile } from "../data/types";
import { fetchWeather, toF, weatherLabel, type Weather } from "../lib/weather";
import WeatherGlyph from "./WeatherGlyph";

// Now, the next three days, and what this month is usually like at a spot.
// Fahrenheit first because the parks are American, Celsius in the title.
const MONTHS = [
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
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function Icon({ code, size = 22 }: { code: number; size?: number }) {
  return <WeatherGlyph code={code} size={size} />;
}

export default function WeatherChip({
  lat,
  lon,
  climate,
  at,
  compact,
  badge,
}: {
  lat: number;
  lon: number;
  climate?: ClimateFile | null;
  at?: string;
  compact?: boolean;
  badge?: boolean; // the tour card: a bigger picture beside the stop's name, one line of typical weather under it
}) {
  const [w, setW] = useState<Weather | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setW(undefined);
    fetchWeather(lat, lon)
      .then((x) => {
        if (live) setW(x);
      })
      .catch(() => {
        if (live) setW(null);
      });
    return () => {
      live = false;
    };
  }, [lat, lon]);
  const month = new Date().getMonth();
  const typical = climate?.months[month];
  if (w === null && !typical) return null;
  if (badge) {
    return (
      <div className="weather as-badge" aria-live="polite">
        {w ? (
          <div
            className="weather-badge"
            title={`${Math.round(w.temp)} °C, ${weatherLabel(w.code)}, wind ${Math.round(w.wind)} km/h`}
          >
            <Icon code={w.code} size={40} />
            <div className="weather-badge-text">
              <strong>{toF(w.temp)}°F</strong>
              <span className="muted small">{weatherLabel(w.code)}</span>
            </div>
          </div>
        ) : w === undefined ? (
          <span className="muted small">Weather…</span>
        ) : null}
        {typical && typical.tmax != null && typical.tmin != null && (
          <div className="weather-typical muted small">
            Usually {toF(typical.tmax)}° / {toF(typical.tmin)}° in {MONTHS[month]}
          </div>
        )}
      </div>
    );
  }
  return (
    <div className={"weather" + (compact ? " compact" : "")} aria-live="polite">
      {w === undefined ? (
        <span className="muted small">Checking the weather…</span>
      ) : w === null ? null : (
        <div
          className="weather-now"
          title={`${Math.round(w.temp)} °C, ${weatherLabel(w.code)}, wind ${Math.round(w.wind)} km/h`}
        >
          <Icon code={w.code} />
          <strong>{toF(w.temp)}°F</strong>
          <span>{weatherLabel(w.code)}</span>
          {!compact && <span className="muted">· wind {Math.round(w.wind * 0.621)} mph</span>}
          {at && !compact && <span className="muted">· at {at}</span>}
        </div>
      )}
      {w && !compact && (
        <div className="weather-days">
          {w.daily.slice(1, 4).map((d) => (
            <div
              key={d.date}
              className="weather-day"
              title={`${weatherLabel(d.code)}; ${Math.round(d.tmax)} / ${Math.round(d.tmin)} °C`}
            >
              <span className="muted small">{DAYS[new Date(d.date + "T12:00:00").getDay()]}</span>
              <Icon code={d.code} />
              <span className="small">
                {toF(d.tmax)}° / {toF(d.tmin)}°
              </span>
              {d.pop != null && d.pop >= 30 && <span className="muted small">{d.pop}% rain</span>}
            </div>
          ))}
        </div>
      )}
      {typical && typical.tmax != null && typical.tmin != null && (
        <div
          className="weather-typical muted small"
          title={`${typical.tmax} / ${typical.tmin} °C, ${typical.precip_mm} mm precipitation, ${typical.snow_cm} cm snow`}
        >
          Typical for {MONTHS[month]}: {toF(typical.tmax)}° / {toF(typical.tmin)}°F, {typical.wet_days} wet day
          {typical.wet_days === 1 ? "" : "s"}
          {typical.snow_cm >= 1 ? `, ${Math.round(typical.snow_cm / 2.54)} in of snow` : ""}
          {climate?.at && !compact ? ` at ${climate.at}` : ""}
        </div>
      )}
    </div>
  );
}
