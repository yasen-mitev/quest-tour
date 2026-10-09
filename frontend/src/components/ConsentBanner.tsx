import { useId } from "react";
import { useConsent } from "../lib/consent";

const TEXTS = {
  player: "This app stores only what it needs to run: your team link and your language choice. Strictly necessary only — no tracking, no third parties.",
  admin: "This app stores only what it needs to run: a cookie for your admin sign-in session. Strictly necessary only — no tracking, no third parties.",
} as const;

/** Cookie notice for both apps, shown as a centred pop-up dialog until answered: the player
 *  app and the admin panel store strictly necessary data only, and the banner records the
 *  answer so future non-essential storage can gate on `useConsent()`. Each app names only
 *  its own storage: the admin sign-in session belongs to the admin text alone. Accept and
 *  Decline are equal choices — both render as the neutral secondary button. */
export function ConsentBanner({ app }: { app: "player" | "admin" }) {
  const { consent, accept, decline } = useConsent();
  const titleId = useId();
  if (consent) return null;
  return (
    <div className="qc-consent-scrim">
      <section className="qc-consent" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <h2 className="qc-consent__title" id={titleId}>About cookies</h2>
        <p className="t-body">
        {TEXTS[app]}{" "}
        <a href="/privacy">Privacy policy</a>
      </p>
        <div className="qc-consent__actions">
          <button type="button" className="qc-btn qc-btn--secondary qc-btn--block" onClick={accept}>Accept</button>
          <button type="button" className="qc-btn qc-btn--secondary qc-btn--block" onClick={decline}>Decline</button>
        </div>
      </section>
    </div>
  );
}
