import { useState } from "react";
import { Icon } from "./Icon";

export const RATING_WORDS: Record<number, string> = {
  1: "Too hard or unclear", 2: "Not great", 3: "It was OK", 4: "Good one", 5: "Loved it!",
};

/** One to five stars for a riddle (issue #38), shown right after it is solved or revealed. Optional and
 *  free: tapping a star saves it at once, tapping another changes it. 48 px targets, gold when chosen. */
export function StarRating({ value, onChange, label = "Rate this riddle" }: {
  value: number | null; onChange(stars: number): void; label?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const lit = hover ?? value ?? 0;
  return (
    <section className="qs-rate" aria-label={label}>
      <p className="qs-eyebrow qs-eyebrow--gold"><Icon name="star" />{label}</p>
      <div className="qs-rate__stars" role="radiogroup" aria-label={label} onMouseLeave={() => setHover(null)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={`${n} star${n === 1 ? "" : "s"}`}
            className={n <= lit ? "qs-rate__star is-on" : "qs-rate__star"}
            onMouseEnter={() => setHover(n)}
            onClick={() => onChange(n)}
          >
            <Icon name="star" />
          </button>
        ))}
      </div>
      <p className="t-caption qs-rate__word">
        {value ? RATING_WORDS[value] : "Tap a star – it helps your host make the riddles better."}
      </p>
    </section>
  );
}

/** Read-only stars for an average, e.g. 4.2 lights four and a bit. */
export function StarsStatic({ value }: { value: number }) {
  return (
    <div className="qs-rate__stars qs-rate__stars--static" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((n) => {
        const fill = Math.max(0, Math.min(1, value - (n - 1)));
        return (
          <span key={n} className="qs-rate__star is-static" style={{ "--fill": `${fill * 100}%` } as React.CSSProperties}>
            <Icon name="star" />
          </span>
        );
      })}
    </div>
  );
}
