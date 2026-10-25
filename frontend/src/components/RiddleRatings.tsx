import type { RiddleRatingRow } from "../api/types";
import { pickText } from "../lib/i18n";
import { Icon } from "./Icon";

/** Rate any completed riddle once the game is over (issue #51). Same free, changeable, per-phone
 *  rating as right after the riddle (#38): tapping a star saves it at once. */
export function RiddleRatings({ riddles, language, onRate }: {
  riddles: RiddleRatingRow[]; language: string; onRate(position: number, stars: number): void;
}) {
  if (riddles.length === 0) return null;
  return (
    <section className="qs-card qs-rate-list" aria-labelledby="rate-riddles-label">
      <p className="qs-eyebrow qs-eyebrow--gold" id="rate-riddles-label"><Icon name="star" />Rate the riddles</p>
      <ul className="qs-rate-list__items">
        {riddles.map((r) => {
          const name = pickText(r.landmark_name, r.landmark_name_i18n, language);
          return (
            <li key={r.position} className="qs-rate-list__row">
              <span className="qs-rate-list__name"><span className="t-caption">{r.number}.</span> {name}</span>
              <div className="qs-rate__stars" role="radiogroup" aria-label={`Rate ${name}`}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} type="button" role="radio" aria-checked={r.rating === n}
                          aria-label={`${n} star${n === 1 ? "" : "s"}`}
                          className={r.rating !== null && n <= r.rating ? "qs-rate__star is-on" : "qs-rate__star"}
                          onClick={() => onRate(r.position, n)}>
                    <Icon name="star" />
                  </button>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
