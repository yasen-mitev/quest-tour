import type { GameState, Task } from "../api/types";

export function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    number: 3, picture_url: "/api/images/x.svg",
    text: "Golden domes shine over the square that bears my name. I was built to honour soldiers who fell for this land's freedom. Who am I?",
    text_i18n: {},
    hints: [
      { number: 1, penalty_minutes: 10, available: true, opened: false, text: null, text_i18n: {} },
      { number: 2, penalty_minutes: 15, available: false, opened: false, text: null, text_i18n: {} },
    ],
    wrong_attempts: 0, reveal_unlocked: false, reveal_unlocks_in_seconds: 1200,
    completion: null, revealed_answer: null, reveal_penalty_minutes: 0, landmark: null, photo_count: 0, compass: null,
    rating: null, ...overrides,
  };
}

export function makeState(overrides: Partial<GameState> = {}): GameState {
  return {
    version: 7, service: false, status: "playing", phase: "task", position: 2,
    game: { name: "Sofia Old Town Quest", intro: "Welcome!\n\nHave fun.", task_count: 8, time_zone: "Europe/Sofia",
            max_duration_minutes: 240, hint_penalties: [10, 15], reveal_after_attempts: 5,
            reveal_after_minutes: 20, reveal_penalty_minutes: 30, available_languages: [] },
    team: { name: "The Explorers" },
    clock: { elapsed_seconds: 4365, running: true, penalty_minutes: 25, remaining_seconds: 10035, warning: false },
    task: makeTask(), results: null, ...overrides,
  };
}

export const NEVSKY = { name: "Alexander Nevsky Cathedral", info: "Built 1882–1912.\n\nOne of the largest.", picture_url: null, name_i18n: {}, info_i18n: {} };
