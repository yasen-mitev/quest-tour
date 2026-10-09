import type { GameState } from "../api/types";
import { Confetti } from "../components/art";
import { GameFrame, type FrameProps } from "../components/GameFrame";
import { Icon } from "../components/Icon";
import { StarRating } from "../components/StarRating";
import { pickText } from "../lib/i18n";

export function CorrectScreen({ state, frame, language, onContinue, onRate }: {
  state: GameState; frame: FrameProps; language: string; onContinue(): void; onRate(stars: number): void;
}) {
  const task = state.task!;
  const landmark = task.landmark;
  const landmarkName = pickText(landmark?.name ?? "", landmark?.name_i18n, language);
  return (
    <GameFrame
      frame={frame}
      mainClassName="qs-main qs-main--center"
      actions={
        <div className="qs-actions">
          <button type="button" className="qc-btn qc-btn--primary qc-btn--block" onClick={onContinue}>
            <Icon name="camera" />Take a photo, create a memory
          </button>
          <p className="t-caption" style={{ textAlign: "center" }}>A team photo unlocks the next riddle.</p>
        </div>
      }
    >
      <Confetti />
      <div className="qs-badge"><Icon name="check" /></div>
      <h1 className="t-display-xl" style={{ marginTop: 12 }}>Correct!</h1>
      <div style={{ display: "grid", gap: 4 }}>
        <p className="t-body t-muted">You explored a new landmark:</p>
        <p className="t-display-l">{landmarkName}</p>
      </div>
      <StarRating value={task.rating} onChange={onRate} />
    </GameFrame>
  );
}
