import type { ReactNode } from "react";
import { useConsent } from "../lib/consent";

const GITHUB_ISSUES = "https://github.com/yasen-mitev/quest-tour/issues";

/** Where the visitor came from: the admin panel opens the legal pages with `?from=admin` so the
 *  Back button can return there; everything else counts as the player app. */
function fromParam(): string | null {
  return new URLSearchParams(window.location.search).get("from");
}

function withFrom(href: string): string {
  const from = fromParam();
  return from ? `${href}?from=${encodeURIComponent(from)}` : href;
}

/** The three legal/contact pages (issues #20, #22, #25): static text screens, no backend — the
 *  content lives here and is edited when it changes. The link row repeats on every page and on
 *  the landing screen, so the legal pages are reachable from the first page and from each other.
 *  `withSettings` adds the Cookie settings item (re-opens the consent dialog); the cover screen
 *  uses it so guests can change their answer from the first page too. */
export function LegalLinks({ withSettings = false }: { withSettings?: boolean }) {
  const { reopen } = useConsent();
  return (
    <footer className="qs-legal" aria-label="Legal and contact">
      <a href={withFrom("/privacy")}>Privacy</a>
      <a href={withFrom("/terms")}>Terms</a>
      <a href={withFrom("/contact")}>Contact</a>
      {withSettings && (
        <button type="button" className="qs-legal__settings" onClick={reopen}>Cookies</button>
      )}
    </footer>
  );
}

function LegalScreen({ title, children }: { title: string; children: ReactNode }) {
  const goBack = () => {
    // Back always returns to the visitor's first page: the admin dashboard when they arrived
    // from the admin panel, otherwise the app root — which reopens the guest's game (the
    // welcome page) when they carry a team link.
    window.location.href = fromParam() === "admin" ? "/admin" : "/";
  };
  return (
    <div className="qs">
      <div className="qs-scroll">
        <main className="qs-main">
          <div className="qs-card">
            <h1 className="t-title">{title}</h1>
            {children}
            <button type="button" className="qc-btn qc-btn--quiet qs-legal__back" onClick={goBack}>
              ← Back
            </button>
          </div>
          <LegalLinks />
        </main>
      </div>
    </div>
  );
}

function Section({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="qs-legal__section">
      <h2 className="t-label">{heading}</h2>
      {children}
    </section>
  );
}

export function PrivacyScreen() {
  return (
    <LegalScreen title="Privacy Policy">
      <Section heading="What stays in your browser">
        <p className="t-body">
          Your team link, your language choice and your cookie-consent answer are stored in your
          browser so the game works the way you left it. This is strictly necessary storage —
          clearing your browser data removes it.
        </p>
      </Section>
      <Section heading="What your host keeps">
        <p className="t-body">
          Your host's server keeps your team name, the photos your team takes during the quest,
          and the game results (times, hints and penalties, and your rank). Photos are collected
          and kept by your host; you won't see them in the app.
        </p>
      </Section>
      <Section heading="What we don't do">
        <p className="t-body">
          No analytics, no tracking, no advertising, no third-party services. See our{" "}
          <a href={withFrom("/contact")}>contact page</a> for data questions.
        </p>
      </Section>
    </LegalScreen>
  );
}

export function TermsScreen() {
  return (
    <LegalScreen title="Terms of Service">
      <Section heading="The game">
        <p className="t-body">
          Quest City Tour is a city quest organised by your host. The app is provided as is,
          without warranty of any kind, and availability is best effort.
        </p>
      </Section>
      <Section heading="Photos">
        <p className="t-body">
          Photos your team uploads are collected and kept by your host, who is responsible for
          them and for what they show.
        </p>
      </Section>
      <Section heading="Team links">
        <p className="t-body">
          Each game link belongs to one team. Please don't share it outside your team.
        </p>
      </Section>
      <Section heading="Results">
        <p className="t-body">
          Times and rankings are recorded as measured by the app; small deviations, for example
          from connectivity or device clocks, are possible.
        </p>
      </Section>
    </LegalScreen>
  );
}

export function ContactScreen() {
  return (
    <LegalScreen title="Contact">
      <p className="t-body">
        Quest City Tour is developed in the open. If something is broken or you have an idea
        that would make the game better, open an issue on GitHub — that is the fastest way to
        reach us.
      </p>
      <div className="qs-legal__buttons">
        <a className="qc-btn qc-btn--secondary" href={`${GITHUB_ISSUES}/new?title=%5BBug%5D%20`}>Report a bug</a>
        <a className="qc-btn qc-btn--secondary" href={`${GITHUB_ISSUES}/new?title=%5BFeature%5D%20`}>Request a feature</a>
      </div>
    </LegalScreen>
  );
}
