import { useEffect, useRef, type CSSProperties } from "react";
import type { Clock } from "../api/types";
import { formatHms, formatLeft, formatPenalty } from "../lib/format";
import { useNow } from "../lib/useNow";
import { Icon } from "./Icon";
import { LanguageToggle } from "./LanguageToggle";

const WARNING_SECONDS = 15 * 60;

export function GameHeader({ clock, position, taskCount, receivedAt, onTimeUp,
                             availableLanguages, language, onLanguageChange }: {
  clock: Clock; position: number; taskCount: number; receivedAt: number; onTimeUp(): void;
  availableLanguages: string[]; language: string; onLanguageChange(lang: string): void;
}) {
  const grace = clock.grace_seconds_remaining;         // issue #49: free-pause countdown
  const paused = grace !== null;
  const now = useNow(clock.running || paused ? 1000 : null);
  const drift = clock.running ? Math.max(0, Math.floor((now - receivedAt) / 1000)) : 0;
  const elapsed = clock.elapsed_seconds + drift;
  const remaining = clock.remaining_seconds === null ? null : Math.max(0, clock.remaining_seconds - drift);
  const graceLeft = paused ? Math.max(0, grace - Math.floor((now - receivedAt) / 1000)) : null;
  const warning = clock.running && remaining !== null && remaining <= WARNING_SECONDS;
  const taskNo = Math.min(position + 1, taskCount);
  const penalty = clock.penalty_minutes > 0 ? formatPenalty(clock.penalty_minutes) : null;

  const firedFor = useRef<number | null>(null);
  useEffect(() => {                                  // the server decides; ask it as soon as a local countdown hits 0
    const due = (clock.running && remaining === 0) || (graceLeft !== null && graceLeft === 0);
    if (due && firedFor.current !== receivedAt) {
      firedFor.current = receivedAt;
      onTimeUp();
    }
  }, [clock.running, remaining, graceLeft, receivedAt, onTimeUp]);

  return (
    <header className={warning ? "qc-header qc-header--warning" : "qc-header"}
            aria-label={warning ? "Game status – time running out" : "Game status"} style={{ flex: "none" }}>
      <div className="qc-header__top">
        <span className="qc-header__clock"><Icon name="clock" />{formatHms(elapsed)}</span>
        <div className="qc-header__right">
          {warning
            ? <span className="qc-header__left">{formatLeft(remaining!)}</span>
            : graceLeft !== null
              ? <span className="qc-header__left">{formatLeft(graceLeft)}</span>
              : penalty && <span className="qc-tag qc-tag--on-dark">{penalty}</span>}
          <LanguageToggle languages={availableLanguages} selected={language} onSelect={onLanguageChange} />
        </div>
      </div>
      <div className="qc-header__progress">
        <span>Task {taskNo} of {taskCount}{warning && penalty ? ` · ${penalty}` : ""}</span>
        <div className="qc-progress qc-progress--seg" role="progressbar" aria-label="Quest progress"
             aria-valuenow={taskNo} aria-valuemin={0} aria-valuemax={taskCount}
             style={{ "--segments": taskCount } as CSSProperties}>
          <span style={{ width: `${(taskNo / taskCount) * 100}%` }} />
        </div>
      </div>
    </header>
  );
}
