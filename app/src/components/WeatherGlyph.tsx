import { weatherIcon } from "../lib/weather";

// Weather as a small picture: drawn inline so it needs no asset, no font and
// nothing from outside the page's security policy. A little motion where it
// reads as weather (rays turn, rain falls, snow drifts), none when the
// visitor asked for reduced motion.
const SUN = "#f5b301";
const SUN_FILL = "#f8c94a";
const CLOUD = "#b6bfcb";
const CLOUD_DARK = "#7c8794";
const RAIN = "#3b82f6";
const SNOW = "#9cc4ea";
const BOLT = "#f59e0b";

function Cloud({ fill = CLOUD, y = 0 }: { fill?: string; y?: number }) {
  return (
    <path
      transform={`translate(0 ${y})`}
      d="M14 34h20a7 7 0 0 0 .8-13.95A10 10 0 0 0 15.6 18.4 7.5 7.5 0 0 0 14 34z"
      fill={fill}
    />
  );
}

export default function WeatherGlyph({ code, size = 32 }: { code: number; size?: number }) {
  const kind = weatherIcon(code);
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 48 48",
    className: `wx wx-${kind}`,
    "aria-hidden": true as const,
  };
  if (kind === "sun") {
    return (
      <svg {...common}>
        <g className="wx-rays" stroke={SUN} strokeWidth="3" strokeLinecap="round">
          {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
            <line key={a} x1="24" y1="5" x2="24" y2="11" transform={`rotate(${a} 24 24)`} />
          ))}
        </g>
        <circle cx="24" cy="24" r="9" fill={SUN_FILL} />
      </svg>
    );
  }
  if (kind === "partly") {
    return (
      <svg {...common}>
        <g className="wx-rays" stroke={SUN} strokeWidth="2.5" strokeLinecap="round">
          {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
            <line key={a} x1="18" y1="4" x2="18" y2="8" transform={`rotate(${a} 18 17)`} />
          ))}
        </g>
        <circle cx="18" cy="17" r="7" fill={SUN_FILL} />
        <Cloud y={2} />
      </svg>
    );
  }
  if (kind === "cloud") {
    return (
      <svg {...common}>
        <Cloud fill={CLOUD_DARK} y={-2} />
        <Cloud y={4} />
      </svg>
    );
  }
  if (kind === "fog") {
    return (
      <svg {...common}>
        <Cloud y={-6} />
        <g stroke={CLOUD_DARK} strokeWidth="2.5" strokeLinecap="round" className="wx-fog">
          <line x1="10" y1="35" x2="34" y2="35" />
          <line x1="16" y1="41" x2="40" y2="41" />
        </g>
      </svg>
    );
  }
  if (kind === "drizzle" || kind === "rain") {
    return (
      <svg {...common}>
        <Cloud fill={CLOUD_DARK} y={-6} />
        <g stroke={RAIN} strokeWidth="2.5" strokeLinecap="round" className="wx-drops">
          <line x1="16" y1="34" x2="14" y2="40" />
          <line x1="24" y1="34" x2="22" y2="40" />
          <line x1="32" y1="34" x2="30" y2="40" />
        </g>
      </svg>
    );
  }
  if (kind === "snow") {
    return (
      <svg {...common}>
        <Cloud y={-6} />
        <g fill={SNOW} className="wx-flakes">
          <circle cx="16" cy="37" r="2.2" />
          <circle cx="24" cy="41" r="2.2" />
          <circle cx="32" cy="37" r="2.2" />
        </g>
      </svg>
    );
  }
  return (
    <svg {...common}>
      <Cloud fill={CLOUD_DARK} y={-6} />
      <path d="M26 28l-6 9h5l-2 8 7-11h-5l2-6z" fill={BOLT} className="wx-bolt" />
    </svg>
  );
}
