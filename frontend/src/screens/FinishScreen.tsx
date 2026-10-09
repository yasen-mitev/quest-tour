import type { GameState } from "../api/types";
import { AppVersion } from "../components/AppVersion";
import { Confetti, CurtainArt } from "../components/art";
import { ConnectionBanner } from "../components/ConnectionBanner";
import type { FrameProps } from "../components/GameFrame";
import { Icon } from "../components/Icon";
import { Leaderboard } from "../components/Leaderboard";
import { Paragraphs } from "../components/Paragraphs";
import { TeamFeedback } from "../components/TeamFeedback";
import { Toast } from "../components/Toast";
import { formatHms, formatPenalty, ordinal } from "../lib/format";

export function FinishScreen({ state, frame, albumUrl, onFeedback = () => {} }: {
  state: GameState; frame: FrameProps; albumUrl?: string; onFeedback?(text: string): Promise<unknown> | void;
}) {
  const results = state.results!;
  const { game, team } = state;
  const total = results.total_seconds ?? 0;
  return (
    <div className="qs">
      {frame.offline && <ConnectionBanner />}
      <div className="qs-scroll">
        <section className="qs-curtain">
          <Confetti />
          <CurtainArt />
          {results.rank !== null && (
            <span className="qs-team">
              <Icon name="trophy" />{results.shared_rank ? "Shared " : ""}{ordinal(results.rank)} place
            </span>
          )}
          <h1 className="t-display-xl" style={{ marginTop: 8 }}>You did it!</h1>
          <p className="t-body">{team.name} finished all {game.task_count} tasks of {game.name}.</p>
        </section>
        <main className="qs-main">
          <section className="qs-card" aria-labelledby="total-label">
            <div style={{ display: "grid", gap: 2 }}>
              <p className="t-caption" id="total-label">Your total time</p>
              <p className="t-timer-xl" style={{ margin: 0 }}>{formatHms(total)}</p>
            </div>
            <dl className="qs-sum">
              <div className="qs-sum__row"><dt>Time on the clock</dt><dd>{formatHms(results.elapsed_seconds)}</dd></div>
              <div className="qs-sum__row"><dt>Hints ({results.hints_used} used)</dt><dd className="pen">{formatPenalty(results.hint_penalty_minutes)}</dd></div>
              <div className="qs-sum__row"><dt>Revealed answers ({results.reveals_used})</dt><dd className="pen">{formatPenalty(results.reveal_penalty_minutes)}</dd></div>
              <div className="qs-sum__row qs-sum__total"><dt>Total</dt><dd>{formatHms(total)}</dd></div>
            </dl>
          </section>
          <Leaderboard rows={results.leaderboard} gameName={game.name} />
          <section className="qs-card qs-host-card" aria-labelledby="host-label">
            <p className="qs-eyebrow qs-eyebrow--gold" id="host-label"><Icon name="gift" />From your host</p>
            <Paragraphs text={results.exit_message} />
          </section>
          <TeamFeedback results={results} onFeedback={onFeedback} />
          {albumUrl && (
            <a className="qc-btn qc-btn--primary qc-btn--block" href={albumUrl}>
              <Icon name="gallery" />Open your memories album
            </a>
          )}
          <AppVersion />
        </main>
      </div>
      {frame.notice && <Toast message={frame.notice} onDone={frame.onNoticeDone} />}
    </div>
  );
}
