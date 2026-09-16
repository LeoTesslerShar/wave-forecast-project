// Small dependency-free inline SVG icons -- no icon library added, consistent with this
// project's deliberately minimal dependency list (react + react-dom only).

export function SunIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="5" fill="#f5a623" />
      <g stroke="#f5a623" strokeWidth="2" strokeLinecap="round">
        <line x1="12" y1="1" x2="12" y2="4" />
        <line x1="12" y1="20" x2="12" y2="23" />
        <line x1="1" y1="12" x2="4" y2="12" />
        <line x1="20" y1="12" x2="23" y2="12" />
        <line x1="4.2" y1="4.2" x2="6.3" y2="6.3" />
        <line x1="17.7" y1="17.7" x2="19.8" y2="19.8" />
        <line x1="4.2" y1="19.8" x2="6.3" y2="17.7" />
        <line x1="17.7" y1="6.3" x2="19.8" y2="4.2" />
      </g>
    </svg>
  );
}

export function MoonIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"
        fill="#2c3e6b"
      />
    </svg>
  );
}

function CloudShape({ fill = "#9aa5b1", x = 0 }) {
  return (
    <path
      transform={`translate(${x},0)`}
      d="M6.5 17a3.5 3.5 0 0 1-.4-6.98A4.5 4.5 0 0 1 14.4 9.1 3.75 3.75 0 0 1 17 17H6.5Z"
      fill={fill}
    />
  );
}

export function CloudyIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <CloudShape fill="#8b95a3" />
    </svg>
  );
}

export function PartlyCloudyIcon({ size = 20, isDay = true }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      {isDay ? (
        <circle cx="16" cy="8" r="4" fill="#f5a623" />
      ) : (
        <path d="M19 8.2A4.3 4.3 0 1 1 13.9 3a3.4 3.4 0 0 0 5.1 5.2Z" fill="#2c3e6b" />
      )}
      <CloudShape fill="#9aa5b1" x="-2" />
    </svg>
  );
}

export function RainIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <CloudShape fill="#8b95a3" />
      <g stroke="#0a6fb5" strokeWidth="1.6" strokeLinecap="round">
        <line x1="8" y1="18" x2="7" y2="21" />
        <line x1="12" y1="18" x2="11" y2="21" />
        <line x1="16" y1="18" x2="15" y2="21" />
      </g>
    </svg>
  );
}

export function FogIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <g stroke="#9aa5b1" strokeWidth="1.8" strokeLinecap="round">
        <line x1="3" y1="9" x2="21" y2="9" />
        <line x1="3" y1="13" x2="21" y2="13" />
        <line x1="3" y1="17" x2="21" y2="17" />
      </g>
    </svg>
  );
}

export function StormIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <CloudShape fill="#6b7280" />
      <path d="M12 13l-2.2 4h2l-1 3.5L14 15h-2.2L13 13h-1Z" fill="#f5a623" />
    </svg>
  );
}

export function SnowIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <CloudShape fill="#9aa5b1" />
      <g stroke="#7dd3fc" strokeWidth="1.6" strokeLinecap="round">
        <line x1="8" y1="18" x2="8" y2="21.5" />
        <line x1="12" y1="18" x2="12" y2="21.5" />
        <line x1="16" y1="18" x2="16" y2="21.5" />
      </g>
    </svg>
  );
}

const WEATHER_ICON_BY_KEY = {
  clear: null, // resolved to Sun/Moon by time of day, below
  partly_cloudy: PartlyCloudyIcon,
  cloudy: CloudyIcon,
  fog: FogIcon,
  rain: RainIcon,
  snow: SnowIcon,
  storm: StormIcon,
};

/** Resolves a weather_icon key (from app/quality/weather.py, via the API) plus
 * time-of-day into one concrete icon. "clear" has no dedicated icon of its own -- it reuses
 * Sun/Moon, since a clear NIGHT sky and a clear DAY sky are different icons for the same
 * condition. Falls back to a plain cloud rather than rendering nothing for an
 * unrecognised/"unknown" key, so missing weather data never looks like a rendering bug. */
export function WeatherIcon({ iconKey, isDay, size = 20 }) {
  if (iconKey === "clear" || !iconKey || iconKey === "unknown") {
    return isDay ? <SunIcon size={size} /> : <MoonIcon size={size} />;
  }
  if (iconKey === "partly_cloudy") return <PartlyCloudyIcon size={size} isDay={isDay} />;
  const Cmp = WEATHER_ICON_BY_KEY[iconKey] || CloudyIcon;
  return <Cmp size={size} />;
}

/** Rotated per wind direction (meteorological "from" bearing) -- points the way the wind
 * is blowing TOWARD, which is the intuitive arrow direction people expect on a map. */
export function WindArrowIcon({ directionDeg, size = 18, color = "#ffffff" }) {
  const rotation = directionDeg != null ? (directionDeg + 180) % 360 : 0;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      style={{ transform: `rotate(${rotation}deg)`, display: "block" }}
    >
      <path d="M12 2 L19 21 L12 16.5 L5 21 Z" fill={color} />
    </svg>
  );
}

export function FacebookIcon({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      <rect width="24" height="24" rx="5" fill="#1877f2" />
      <path
        d="M15.5 8.5h-1.6c-.3 0-.6.3-.6.7v1.6h2.1l-.3 2.1h-1.8V19h-2.3v-6.1H9.4v-2.1h1.6V9c0-1.6 1-2.7 2.6-2.7h1.9v2.2Z"
        fill="#fff"
      />
    </svg>
  );
}

export function WhatsAppIcon({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      <rect width="24" height="24" rx="5" fill="#25d366" />
      <path
        d="M12 5.5a6.5 6.5 0 0 0-5.6 9.8L5.5 18.5l3.3-.9A6.5 6.5 0 1 0 12 5.5Zm0 1.3a5.2 5.2 0 1 1-2.7 9.6l-.2-.1-2 .5.5-1.9-.1-.2A5.2 5.2 0 0 1 12 6.8Zm-2.4 2.6c-.1 0-.4 0-.5.3-.2.3-.7.7-.7 1.6s.7 1.9.8 2c.1.1 1.4 2.2 3.4 3 .5.2.8.3 1.1.2.4-.1 1.2-.5 1.4-.9.2-.4.2-.8.1-.9-.1-.1-.2-.2-.5-.3s-1.2-.6-1.4-.7c-.2-.1-.3-.1-.5.1s-.6.7-.8.9c-.1.2-.3.2-.5.1-.3-.1-1.1-.4-2.1-1.3-.8-.7-1.3-1.5-1.4-1.8-.1-.2 0-.4.1-.5l.4-.4c.1-.1.1-.2.2-.4 0-.1 0-.3 0-.4s-.5-1.2-.7-1.7c-.2-.4-.4-.4-.5-.4h-.4Z"
        fill="#fff"
      />
    </svg>
  );
}
