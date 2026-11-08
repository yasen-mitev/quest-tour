export interface Coordinates {
  lat: number;
  lon: number;
}

export interface Landmark {
  id: number;
  key: string;
  name: string;
  name_i18n: Record<string, string> | null;
  task: string;
  task_i18n: Record<string, string> | null;
  accepted_answers: string[];
  hint1: string | null;
  hint1_i18n: Record<string, string> | null;
  hint2: string | null;
  hint2_i18n: Record<string, string> | null;
  tourist_info: string;
  tourist_info_i18n: Record<string, string> | null;
  coordinates: Coordinates | null;
  task_image_url: string | null;
  info_image_url: string | null;
  updated_at: string;
}

export interface RevealSettings {
  attempts: number;
  minutes: number;
  penalty_minutes: number;
}

export interface Game {
  id: number;
  key: string;
  name: string;
  intro: string;
  time_zone: string;
  max_duration_minutes: number;
  reveal: RevealSettings;
  /** Offered on the website's request form (issue #61) */
  requestable: boolean;
  updated_at: string;
  task_landmark_ids: number[];
}

export interface Team {
  id: number;
  key: string;
  name: string;
  participants: number | null;
  updated_at: string;
}

export interface AssignmentCreate {
  game_id: number;
  valid_from: string;
  valid_until: string;
  exit_message: string;
}

export interface AssignmentOut {
  id: number;
  game_id: number;
  game_name: string;
  valid_from: string;
  valid_until: string;
  exit_message: string;
  token_issued: boolean;
  issued_at: string | null;
  updated_at: string;
}

export interface TokenReveal {
  assignment_id: number;
  token: string;
  url: string;
}

/** A game play request from the website (issue #61) */
export type GameRequestStatus = "pending" | "approved" | "rejected";
export type GameRequestFilter = GameRequestStatus | "all";

export interface GameRequestListItem {
  id: number;
  created_at: string;
  contact_name: string;
  game_id: number | null;
  /** null when the game is gone */
  game_name: string | null;
  /** YYYY-MM-DD */
  play_date: string;
  team_count: number;
  status: GameRequestStatus;
}

export interface GameRequestTeam {
  name: string;
  key: string;
  participants: number | null;
  /** Resolved (the play-date default when not set); null only when the game is gone */
  valid_from: string | null;
  valid_until: string | null;
  /** Set once the request is approved */
  team_id: number | null;
}

export interface GameRequestDetail {
  id: number;
  created_at: string;
  updated_at: string;
  status: GameRequestStatus;
  game_id: number | null;
  game_name: string | null;
  game_time_zone: string | null;
  play_date: string;
  contact_name: string;
  contact_email: string | null;
  contact_phone: string | null;
  message: string | null;
  /** Resolved: the request's own, else the default */
  exit_message: string;
  terms_accepted_at: string;
  terms_version: string;
  decided_at: string | null;
  decided_by: string | null;
  teams: GameRequestTeam[];
}

export interface GameRequestTeamInput {
  name: string;
  key: string;
  participants: number | null;
  /** In the game's time zone when without an offset; null = the play-date default */
  valid_from: string | null;
  valid_until: string | null;
}

export interface GameRequestUpdate {
  game_id: number;
  /** null = the default exit message */
  exit_message: string | null;
  teams: GameRequestTeamInput[];
  seen_at?: string;
}

/** What the players thought (issue #38) */
export interface RiddleRatingOut { landmark_id: number; landmark_name: string; average: number; count: number; }
export interface TeamCommentOut { id: number; team_name: string; game_name: string; submitted_at: string; text: string; }
export interface FeedbackOut { riddles: RiddleRatingOut[]; comments: TeamCommentOut[]; }

/** A stored memories-album PDF (issue #33) */
export interface AlbumFileOut {
  id: number;
  size_bytes: number;
  generated_at: string;
  deleted_at: string | null;
  url: string;
}

/** A run that has ended, with its album if one was generated */
export interface AlbumRowOut {
  assignment_id: number;
  team_name: string;
  game_name: string;
  ended_at: string;
  end_reason: "finished" | "max_duration" | "window_closed";
  photo_count: number;
  album: AlbumFileOut | null;
}

export interface TeamPhotoOut {
  id: number;
  team_name: string;
  game_name: string;
  uploaded_at: string;
  url: string;
}

export interface ConflictBody {
  entity: string;
  current: { id: number; updated_at: string };
}

export type LandmarkInput = Omit<Landmark, "id" | "updated_at" | "task_image_url" | "info_image_url">;
export type GameInput = Omit<Game, "id" | "updated_at" | "task_landmark_ids">;
export type TeamInput = Omit<Team, "id" | "updated_at">;
