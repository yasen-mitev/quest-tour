import { useState, type FormEvent } from "react";
import type { Results } from "../api/types";
import { Icon } from "./Icon";
import { StarsStatic } from "./StarRating";

/** The end of the game (issue #38): the team's average over its riddle ratings, and a box for a word to
 *  the host. One comment per team; once sent, every phone sees the thank-you instead of the form. */
export function TeamFeedback({ results, onFeedback }: {
  results: Pick<Results, "average_rating" | "ratings_count" | "feedback_submitted">;
  onFeedback(text: string): Promise<unknown> | void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const average = results.average_rating;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || text.trim() === "") return;
    setBusy(true);
    try { await onFeedback(text.trim()); } finally { setBusy(false); }
  }

  return (
    <>
      <section className="qs-card qs-feedback" aria-labelledby="rating-label">
        <p className="qs-eyebrow qs-eyebrow--gold" id="rating-label"><Icon name="star" />Your riddle ratings</p>
        {average === null ? (
          <p className="t-body">Your team didn't rate the riddles this time.</p>
        ) : (
          <div className="qs-feedback__average">
            <p className="t-timer-xl qs-feedback__number">{average.toFixed(1)}</p>
            <div>
              <StarsStatic value={average} />
              <p className="t-caption">Your average rating, from {results.ratings_count} rating{results.ratings_count === 1 ? "" : "s"}</p>
            </div>
          </div>
        )}
      </section>
      <section className="qs-card" aria-labelledby="comment-label">
        <p className="qs-eyebrow" id="comment-label"><Icon name="riddle" />A word for your host</p>
        {results.feedback_submitted ? (
          <p className="t-body"><strong>Thank you for your feedback!</strong> Your host will read it.</p>
        ) : (
          <form className="qs-feedback__form" onSubmit={submit}>
            <label className="qc-field">
              <span className="qc-field__label">Any additional comments?</span>
              <textarea className="qc-input qs-feedback__text" rows={4} maxLength={1000} value={text}
                        placeholder="What did you enjoy, what could be better?"
                        onChange={(e) => setText(e.target.value)} />
            </label>
            <button type="submit" className="qc-btn qc-btn--primary qc-btn--block" disabled={busy || text.trim() === ""}>
              <Icon name="arrow" />Send to your host
            </button>
          </form>
        )}
      </section>
    </>
  );
}
