// Live weather from Open-Meteo: free, keyless, CC BY 4.0. Fetched in the
// browser when a park or a place is looked at, never stored; a short cache
// keeps a tour from asking twice for the same spot. Typical weather by month
// is the pipeline's job (climate.json); this file is only about now.
export interface WeatherDay {
  date: string;
  code: number;
  tmax: number;
  tmin: number;
  pop: number | null;
}
export interface Weather {
  time: string;
  temp: number;
  code: number;
  wind: number;
  precip: number;
  tz: string;
  daily: WeatherDay[];
}

// FORECAST_URL — BORROWED (Open-Meteo forecast API)
const FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
// FORECAST_DAYS — ARBITRARY (today and the next three: what a visitor plans around)
const FORECAST_DAYS = 4;
// CACHE_MS — ARBITRARY (the current conditions update every quarter hour upstream)
const CACHE_MS = 10 * 60 * 1000;
const cache = new Map<string, { at: number; w: Weather }>();

export async function fetchWeather(lat: number, lon: number): Promise<Weather> {
  const key = `${lat.toFixed(2)},${lon.toFixed(2)}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.w;
  const url =
    `${FORECAST_URL}?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}` +
    "&current=temperature_2m,weather_code,wind_speed_10m,precipitation" +
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max" +
    `&timezone=auto&forecast_days=${FORECAST_DAYS}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`weather: HTTP ${res.status}`);
  const j = (await res.json()) as {
    timezone: string;
    current: {
      time: string;
      temperature_2m: number;
      weather_code: number;
      wind_speed_10m: number;
      precipitation: number;
    };
    daily: {
      time: string[];
      weather_code: number[];
      temperature_2m_max: number[];
      temperature_2m_min: number[];
      precipitation_probability_max: (number | null)[];
    };
  };
  const w: Weather = {
    time: j.current.time,
    temp: j.current.temperature_2m,
    code: j.current.weather_code,
    wind: j.current.wind_speed_10m,
    precip: j.current.precipitation,
    tz: j.timezone,
    daily: j.daily.time.map((date, i) => ({
      date,
      code: j.daily.weather_code[i],
      tmax: j.daily.temperature_2m_max[i],
      tmin: j.daily.temperature_2m_min[i],
      pop: j.daily.precipitation_probability_max[i] ?? null,
    })),
  };
  cache.set(key, { at: Date.now(), w });
  return w;
}

// WMO weather interpretation codes, as Open-Meteo documents them.
export function weatherLabel(code: number): string {
  if (code === 0) return "Clear";
  if (code === 1) return "Mainly clear";
  if (code === 2) return "Partly cloudy";
  if (code === 3) return "Overcast";
  if (code === 45 || code === 48) return "Fog";
  if (code >= 51 && code <= 57) return "Drizzle";
  if (code >= 61 && code <= 67) return "Rain";
  if (code >= 71 && code <= 77) return "Snow";
  if (code >= 80 && code <= 82) return "Showers";
  if (code === 85 || code === 86) return "Snow showers";
  if (code >= 95) return "Thunderstorm";
  return "Unsettled";
}
export type WeatherIcon = "sun" | "partly" | "cloud" | "fog" | "drizzle" | "rain" | "snow" | "storm";
export function weatherIcon(code: number): WeatherIcon {
  if (code === 0) return "sun";
  if (code <= 2) return "partly";
  if (code === 3) return "cloud";
  if (code === 45 || code === 48) return "fog";
  if (code >= 51 && code <= 57) return "drizzle";
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return "rain";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code >= 95) return "storm";
  return "cloud";
}
export const toF = (c: number): number => Math.round((c * 9) / 5 + 32);
