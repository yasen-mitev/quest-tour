/** The memories album (issue #33): what GET /api/play/{token}/album returns once the run has ended.
 *  One chapter per task the team completed, with the landmark, its story and every photo taken there,
 *  plus the facts of the day. Mirrors AlbumOut in backend/questtour/api/schemas.py. */

export interface AlbumPhoto {
  id: number;
  url: string;                 // /api/play/{token}/photos/{id}; answers only once the run has ended
  taken_at: string;            // ISO-8601, UTC; shown in the game's time zone
}

export interface AlbumChapter {
  number: number;              // 1-based task number
  landmark: string;
  landmark_i18n: Record<string, string>;
  story: string;               // the landmark's tourist info, paragraphs separated by blank lines
  story_i18n: Record<string, string>;
  reached_at: string;          // when the team completed the task (ISO-8601, UTC)
  seconds: number | null;      // riddle time, shown → solved (breaks between riddles excluded); null if never shown
  hints: number;               // hints and compasses opened on this riddle (R-12)
  penalty_minutes: number;     // hint, compass and reveal minutes charged on this riddle
  photos: AlbumPhoto[];
}

export interface Album {
  game: string;
  team: string;
  time_zone: string;
  played_on: string;           // the start of the run (ISO-8601, UTC)
  ended_at: string;
  end_reason: "finished" | "max_duration" | "window_closed";
  task_count: number;
  total_seconds: number | null;   // null unless the run finished
  rank: number | null;
  shared_rank: boolean;
  host_message: string;
  chapters: AlbumChapter[];
}
