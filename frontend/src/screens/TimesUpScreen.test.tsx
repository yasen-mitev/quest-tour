import { render, screen } from "@testing-library/react";
import { makeState } from "../test/fixtures";
import { TimesUpScreen } from "./TimesUpScreen";

const frame = { header: null, offline: false, notice: null, onNoticeDone: () => {} };
const results = (end_reason: "max_duration" | "window_closed") => ({
  elapsed_seconds: 14400, hints_used: 0, hint_penalty_minutes: 0, reveals_used: 0, reveal_penalty_minutes: 0,
  total_seconds: null, rank: null, shared_rank: false, tasks_completed: 5, end_reason,
  exit_message: "Thank you!", average_rating: null, ratings_count: 0, feedback_submitted: false,
  leaderboard: [{ rank: 1, team_name: "Night Owls", total_seconds: 9665, hints_used: 1, is_you: false }],
});
const state = (reason: "max_duration" | "window_closed") =>
  makeState({ status: "timed_out", phase: "results", clock: null, task: null, results: results(reason) });

it("shows progress and the max-duration copy, and the team is not on the board", () => {
  render(<TimesUpScreen state={state("max_duration")} frame={frame} />);
  expect(screen.getByText("Time's up!")).toBeInTheDocument();
  expect(screen.getByText("Thanks for playing. The 4-hour limit for this game has been reached.")).toBeInTheDocument();
  expect(screen.getByText("5 of 8")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Tasks completed" })).toHaveAttribute("aria-valuenow", "5");
  expect(screen.getByText("Only teams that complete every task are ranked, so The Explorers aren't on the leaderboard this time.")).toBeInTheDocument();
  expect(screen.queryByText("You")).toBeNull();
});

it("shows the window-closed copy", () => {
  render(<TimesUpScreen state={state("window_closed")} frame={frame} />);
  expect(screen.getByText("Thanks for playing. The time window for this game has closed.")).toBeInTheDocument();
});
