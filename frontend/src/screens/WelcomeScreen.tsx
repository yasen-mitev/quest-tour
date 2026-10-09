import { useState, type ReactNode } from "react";
import type { GameState } from "../api/types";
import { AppVersion } from "../components/AppVersion";
import { LanguageToggle } from "../components/LanguageToggle";
import { WelcomeSkyline } from "../components/art";
import { ConfirmSheet } from "../components/ConfirmSheet";
import { ConnectionBanner } from "../components/ConnectionBanner";
import type { FrameProps } from "../components/GameFrame";
import { Icon, type IconName } from "../components/Icon";
import { Paragraphs } from "../components/Paragraphs";
import { Toast } from "../components/Toast";
import { useConsent } from "../lib/consent";
import { formatHours, formatPenalty } from "../lib/format";

export function WelcomeScreen({ state, frame, language, onLanguageChange, onStart }: {
  state: GameState; frame: FrameProps; language: string; onLanguageChange(lang: string): void;
  onStart(): Promise<unknown> | void;
}) {
  const { game } = state;
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const { consent, reopen } = useConsent();
  const limit = formatHours(game.max_duration_minutes);

  async function start() {
    setBusy(true);
    await onStart();
    setBusy(false);
    setConfirming(false);
  }

  const rule = (icon: IconName, content: ReactNode, gold = false) => (
    <li>
      <span className={gold ? "ic ic--gold" : "ic"}><Icon name={icon} /></span>
      <span>{content}</span>
    </li>
  );

  return (
    <div className="qs">
      {frame.offline && <ConnectionBanner />}
      <div className="qs-scroll" inert={confirming}>
        <section className="qs-hero">
          <div className="qs-langbar">
            <LanguageToggle languages={game.available_languages} selected={language} onSelect={onLanguageChange} />
          </div>
          <WelcomeSkyline />
          <p className="qs-hero__kicker">A city quest in {game.task_count} riddles</p>
          <h1 className="t-display-l">{game.name}</h1>
        </section>
        <main className="qs-main">
          <div className="qs-card"><Paragraphs text={game.intro} /></div>
          <div className="qs-card">
            <h2 className="t-title">How it works</h2>
            <ul className="qs-rules">
              {rule("list", "Tasks are played in order – solve one to unlock the next.")}
              {rule("clock", `The clock starts when you tap Start and runs without pause. You have up to ${limit}.`)}
              {rule("bulb", <>Stuck? Hint 1 adds <span className="qc-tag">{formatPenalty(game.hint_penalties[0])}</span>, hint 2 adds <span className="qc-tag">{formatPenalty(game.hint_penalties[1])}</span>.</>, true)}
              {rule("flag", <>Giving up on a task shows the answer and adds <span className="qc-tag">{formatPenalty(game.reveal_penalty_minutes)}</span>.</>, true)}
              {rule("camera", "Take a team photo at every landmark to unlock the next riddle.")}
            </ul>
          </div>
          <div className="qs-note">
            <Icon name="shield" />
            <p className="t-body"><strong>About your photos.</strong> Photos you upload are collected and kept by your host. You won't see them in the app.</p>
          </div>
          {/* The cookie notice is the other privacy statement — keep the re-open entry next to it,
              shown only once the banner has been answered (an open banner makes it a no-op) */}
          {consent && (
            <div className="qs-cookie-settings">
              <button type="button" className="qc-btn qc-btn--quiet" onClick={reopen}>Cookie settings</button>
            </div>
          )}
        </main>
      </div>
      <div className="qs-actions-slot" inert={confirming}>
        <div className="qs-actions">
          <button type="button" className="qc-btn qc-btn--primary qc-btn--block" onClick={() => setConfirming(true)}>Start the quest</button>
          <p className="t-caption" style={{ textAlign: "center" }}>You'll confirm before the clock starts.</p>
          <AppVersion />
        </div>
      </div>
      {frame.notice && <Toast message={frame.notice} onDone={frame.onNoticeDone} />}
      {confirming && (
        <ConfirmSheet
          title="Start the clock?"
          body="It can't be paused. Every team member's phone will start too."
          cost={<><Icon name="clock" size={20} />You have up to {limit} to finish.</>}
          confirmLabel="Start"
          busy={busy}
          onConfirm={start}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
