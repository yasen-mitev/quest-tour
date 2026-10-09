export type Status = "not_started" | "playing" | "finished" | "timed_out";
export type Phase = "task" | "photo" | "info" | "results";
export type Outcome = "ok" | "already_started" | "correct" | "wrong" | "stale" | "locked" | "not_available" | "game_over";

export interface Hint { number: 1 | 2; penalty_minutes: number; available: boolean; opened: boolean; text: string | null; text_i18n: Record<string, string>; }
export interface Compass { opened: boolean; lat: number; lon: number; penalty_minutes: number; }
export interface LandmarkInfo { name: string; info: string; picture_url: string | null; name_i18n: Record<string, string>; info_i18n: Record<string, string>; }
export interface Task {
  number: number; text: string; text_i18n: Record<string, string>; picture_url: string | null; hints: Hint[]; wrong_attempts: number;
  reveal_unlocked: boolean; reveal_unlocks_in_seconds: number | null;
  completion: "answered" | "revealed" | null; revealed_answer: string | null; reveal_penalty_minutes: number;
  landmark: LandmarkInfo | null; photo_count: number; compass: Compass | null;
  rating: number | null;          // this phone's 1–5 stars for the riddle (issue #38), once it is completed
}
export interface Clock { elapsed_seconds: number; running: boolean; penalty_minutes: number; remaining_seconds: number | null; warning: boolean; }
export interface GameInfo {
  name: string; intro: string; task_count: number; time_zone: string; max_duration_minutes: number;
  hint_penalties: number[]; reveal_after_attempts: number; reveal_after_minutes: number; reveal_penalty_minutes: number;
  available_languages: string[];
}
export interface LeaderboardRow { rank: number; team_name: string; total_seconds: number; hints_used: number; is_you: boolean; }
export interface Results {
  elapsed_seconds: number; hints_used: number; hint_penalty_minutes: number; reveals_used: number;
  reveal_penalty_minutes: number; total_seconds: number | null; rank: number | null; shared_rank: boolean;
  tasks_completed: number; end_reason: "finished" | "max_duration" | "window_closed";
  exit_message: string; leaderboard: LeaderboardRow[];
  average_rating: number | null;  // the team's average over its riddle ratings (issue #38), null without any
  ratings_count: number;
  feedback_submitted: boolean;    // the team's closing comment has been sent
}
export interface GameState {
  version: number; service: boolean; status: Status; phase: Phase | null; position: number; game: GameInfo; team: { name: string };
  clock: Clock | null; task: Task | null; results: Results | null;
}
export interface ActionResult { outcome: Outcome; state: GameState; }
export interface LinkNotValidInfo {
  code: "link_not_valid"; reason: "unknown" | "not_yet" | "expired";
  opens_at: string | null; expired_at: string | null; time_zone: string | null;
}
