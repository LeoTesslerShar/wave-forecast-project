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
