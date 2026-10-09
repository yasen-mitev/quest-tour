import { useConsent } from "../lib/consent";

/** Cookie notice for both apps: the player app and the admin panel store strictly necessary
 *  data only (the team link, the language choice, the admin sign-in session cookie), and the
 *  banner records the answer so future non-essential storage can gate on `useConsent()`.
 *  Accept and Decline are equal choices — both render as the neutral secondary button — and
 *  nothing else on the page is blocked before answering. */
export function ConsentBanner() {
  const { consent, accept, decline } = useConsent();
  if (consent) return null;
  return (
    <section className="qc-consent" aria-label="Cookie notice">
      <p className="t-caption">
        <strong>About cookies.</strong> This app stores only what it needs to run: a cookie for the
        admin sign-in session, your team link and your language choice. Strictly necessary only —
        no tracking, no third parties.
      </p>
      <div className="qc-consent__actions">
        <button type="button" className="qc-btn qc-btn--secondary" onClick={accept}>Accept</button>
        <button type="button" className="qc-btn qc-btn--secondary" onClick={decline}>Decline</button>
      </div>
    </section>
  );
}
