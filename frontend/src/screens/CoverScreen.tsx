import type { GameState } from "../api/types";
import { AppVersion } from "../components/AppVersion";
import { WelcomeSkyline } from "../components/art";
import { ConnectionBanner } from "../components/ConnectionBanner";
import type { FrameProps } from "../components/GameFrame";
import { Icon } from "../components/Icon";
import { LanguageToggle } from "../components/LanguageToggle";
import { Toast } from "../components/Toast";
import { LegalLinks } from "./LegalScreens";

/** The first screen of a team link before the game starts: the skyline, the titles and one button that
 *  opens the Welcome page (intro, rules, Start). It is shown once per page load; nothing is sent to the server. */
export function CoverScreen({ state, frame, language, onLanguageChange, onContinue }: {
  state: GameState; frame: FrameProps; language: string; onLanguageChange(lang: string): void; onContinue(): void;
}) {
  const { game, team } = state;
  return (
    <div className="qs">
      {frame.offline && <ConnectionBanner />}
      <section className="qs-cover" aria-label={game.name}>
        <div className="qs-langbar qs-cover__bar">
          <LanguageToggle languages={game.available_languages} selected={language} onSelect={onLanguageChange} />
        </div>
        <div className="qs-cover__art"><WelcomeSkyline big /></div>
        <div className="qs-cover__text">
          <p className="qs-hero__kicker">A city quest in {game.task_count} riddles</p>
          <h1 className="t-display-xl">{game.name}</h1>
          <span className="qs-team"><Icon name="team" />Welcome, {team.name}</span>
        </div>
      </section>
      <div className="qs-actions qs-actions--cover">
        <button type="button" className="qc-btn qc-btn--gold qc-btn--block" onClick={onContinue}>How it works<Icon name="arrow" /></button>
        <LegalLinks />
        <AppVersion inverse />
      </div>
      {frame.notice && <Toast message={frame.notice} onDone={frame.onNoticeDone} />}
    </div>
  );
}
