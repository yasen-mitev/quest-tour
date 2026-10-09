import type { GameState } from "../api/types";
import { GameFrame, type FrameProps } from "../components/GameFrame";
import { Icon } from "../components/Icon";
import { StarRating } from "../components/StarRating";
import { formatPenalty } from "../lib/format";
import { pickText } from "../lib/i18n";

export function RevealedScreen({ state, frame, language, onContinue, onRate }: {
  state: GameState; frame: FrameProps; language: string; onContinue(): void; onRate(stars: number): void;
}) {
  const task = state.task!;
  const landmarkName = pickText(task.landmark?.name ?? "the landmark", task.landmark?.name_i18n, language);
  const recap = pickText(task.text, task.text_i18n, language);
  return (
    <GameFrame
      frame={frame}
      mainClassName="qs-main qs-main--top-lg"
      actions={
        <div className="qs-actions">
          <button type="button" className="qc-btn qc-btn--primary qc-btn--block" onClick={onContinue}>
            Continue<Icon name="arrow" />
          </button>
        </div>
      }
    >
      <section className="qs-answer" aria-labelledby="answer-label">
        <p className="qs-eyebrow qs-eyebrow--gold" id="answer-label"><Icon name="flag" />The answer</p>
        <p className="t-display-l">{task.revealed_answer}</p>
        <span className="qc-tag" style={{ justifySelf: "start" }}>
          {formatPenalty(task.reveal_penalty_minutes)} added
        </span>
      </section>
      <p className="t-body">Head there now – a team photo at {landmarkName} unlocks the next riddle.</p>
      <div className="qs-group" style={{ gap: 8 }}>
        <p className="qs-eyebrow qs-eyebrow--muted"><Icon name="riddle" />The riddle was</p>
        <p className="t-body t-muted">{recap}</p>
      </div>
      <StarRating value={task.rating} onChange={onRate} />
    </GameFrame>
  );
}
