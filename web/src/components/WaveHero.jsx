/** A simple blue banner with a wave-shaped bottom edge, centered title + subtitle --
 * used at the top of a beach's own page (the beach name + today's date). The "wave" is one
 * decorative SVG path cut out of the bottom of the blue rectangle, not a functional chart. */
export default function WaveHero({ title, subtitle }) {
  return (
    <div className="beach-hero">
      <div className="beach-hero-text">
        <h2>{title}</h2>
        {subtitle && <span className="beach-hero-subtitle">{subtitle}</span>}
      </div>
      <svg className="beach-hero-wave" viewBox="0 0 400 24" preserveAspectRatio="none">
        <path
          d="M0,12 C50,24 100,0 150,12 C200,24 250,0 300,12 C350,24 400,0 400,12 L400,24 L0,24 Z"
          fill="var(--bg)"
        />
      </svg>
    </div>
  );
}
