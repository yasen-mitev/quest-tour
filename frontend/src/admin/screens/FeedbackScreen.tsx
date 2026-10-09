import { useEffect, useState } from "react";
import { StarsStatic } from "../../components/StarRating";
import { adminApi, getServerReference, isServerError } from "../api";
import type { FeedbackOut } from "../types";

/** What the players thought (issue #38): the average stars each riddle got across every team, best
 *  first, and the words teams left for the host at the end of their game, newest first. */
export function FeedbackScreen() {
  const [data, setData] = useState<FeedbackOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.feedback()
      .then(setData)
      .catch((err) => {
        if (isServerError(err)) setServerError(getServerReference(err) ?? "Server error");
        else setError("Could not load feedback.");
      });
  }, []);

  return (
    <div className="admin-section">
      <h1 className="t-title">Feedback</h1>
      {error && <p className="qc-field__error">{error}</p>}
      {serverError && <p className="qc-field__error">Server reference: {serverError}</p>}
      {!data && !error && !serverError && <p className="t-body">Loading…</p>}
      {data && (
        <>
          <h2 className="t-body"><strong>Riddle ratings</strong></h2>
          {data.riddles.length === 0 ? (
            <p className="t-body">No riddle has been rated yet.</p>
          ) : (
            <ul className="admin-list" aria-label="Riddle ratings">
              {data.riddles.map((r) => (
                <li key={r.landmark_id} className="admin-list-item">
                  <div>
                    <strong className="t-body">{r.landmark_name}</strong>
                    <span className="t-caption"> — {r.count} rating{r.count === 1 ? "" : "s"}</span>
                  </div>
                  <div className="admin-row-actions admin-rating">
                    <StarsStatic value={r.average} />
                    <span className="t-body"><strong>{r.average.toFixed(1)}</strong></span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <h2 className="t-body"><strong>Words from the teams</strong></h2>
          {data.comments.length === 0 ? (
            <p className="t-body">No team has left a comment yet.</p>
          ) : (
            <ul className="admin-list" aria-label="Team comments">
              {data.comments.map((c) => (
                <li key={c.id} className="admin-list-item admin-comment">
                  <div>
                    <strong className="t-body">{c.team_name}</strong>
                    <span className="t-caption"> — {c.game_name} · {new Date(c.submitted_at).toLocaleString()}</span>
                    <p className="t-body admin-comment__text">{c.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
