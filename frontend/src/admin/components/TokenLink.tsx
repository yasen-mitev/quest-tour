import type { TokenReveal } from "../types";

/** A freshly issued play link with a Copy button; the token is shown only this once. */
export function TokenLink({ reveal, busy = false }: { reveal: TokenReveal; busy?: boolean }) {
  return (
    <div className="admin-row-actions">
      <a className="t-body" href={reveal.url} target="_blank" rel="noreferrer">
        {reveal.url}
      </a>
      <button
        type="button"
        className="qc-btn qc-btn--secondary"
        onClick={() => navigator.clipboard.writeText(reveal.url)}
        disabled={busy}
      >
        Copy
      </button>
    </div>
  );
}
