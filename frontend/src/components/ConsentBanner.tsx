import { useConsent } from "../lib/consent";

const TEXTS = {
  player: "This app stores only what it needs to run: your team link and your language choice. Strictly necessary only — no tracking, no third parties.",
  admin: "This app stores only what it needs to run: a cookie for your admin sign-in session. Strictly necessary only — no tracking, no third parties.",
} as const;

/** Cookie notice for both apps: the player app and the admin panel store strictly necessary
 *  data only, and the banner records the answer so future non-essential storage can gate on
 *  `useConsent()`. Each app names only its own storage: the admin sign-in session belongs to
 *  the admin text alone. Accept and Decline are equal choices — both render as the neutral
 *  secondary button — and nothing else on the page is blocked before answering. */
export function ConsentBanner({ app }: { app: "player" | "admin" }) {
  const { consent, accept, decline } = useConsent();
  if (consent) return null;
  return (
    <section className="qc-consent" aria-label="Cookie notice">
      <p className="t-caption">
        <strong>About cookies.</strong> {TEXTS[app]}
      </p>
      <div className="qc-consent__actions">
        <button type="button" className="qc-btn qc-btn--secondary" onClick={accept}>Accept</button>
        <button type="button" className="qc-btn qc-btn--secondary" onClick={decline}>Decline</button>
      </div>
    </section>
  );
}
