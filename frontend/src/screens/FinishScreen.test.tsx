import { render, screen } from "@testing-library/react";
import { makeState } from "../test/fixtures";
import { FinishScreen } from "./FinishScreen";

const frame = { header: null, offline: false, notice: null, onNoticeDone: () => {} };
const results = {
  elapsed_seconds: 8610, hints_used: 3, hint_penalty_minutes: 35, reveals_used: 0, reveal_penalty_minutes: 0,
  total_seconds: 10710, rank: 2, shared_rank: true, tasks_completed: 8, end_reason: "finished" as const,
  exit_message: "Thank you for exploring Sofia with us!", average_rating: 4.2, ratings_count: 6, feedback_submitted: false,
  leaderboard: [
    { rank: 1, team_name: "Night Owls", total_seconds: 9665, hints_used: 1, is_you: false },
    { rank: 2, team_name: "The Explorers", total_seconds: 10710, hints_used: 3, is_you: true },
    { rank: 2, team_name: "Map Breakers", total_seconds: 10710, hints_used: 2, is_you: false },
  ],
};

it("shows the shared place, the breakdown, the highlighted row and the host message", () => {
  const { container } = render(<FinishScreen state={makeState({ status: "finished", phase: "results", clock: null, task: null, results })} frame={frame} />);
  expect(screen.getByText("Shared 2nd place")).toBeInTheDocument();
  expect(screen.getByText("You did it!")).toBeInTheDocument();
  expect(screen.getByText("The Explorers finished all 8 tasks of Sofia Old Town Quest.")).toBeInTheDocument();
  expect(screen.getByText("Hints (3 used)")).toBeInTheDocument();
  expect(screen.getByText("+35 min")).toBeInTheDocument();
  expect(screen.getByText("Revealed answers (0)")).toBeInTheDocument();
  expect(screen.getAllByText("02:58:30").length).toBeGreaterThanOrEqual(2);
  expect(container.querySelector("tr.is-you")).toHaveTextContent("You");
  expect(screen.getByText("Thank you for exploring Sofia with us!")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /continue|next/i })).toBeNull();   // the game is over
});

it("links to the memories album when the app knows the link (issue #33)", () => {
  const state = makeState({ status: "finished", phase: "results", clock: null, task: null, results });
  render(<FinishScreen state={state} frame={frame} albumUrl="/album/explorers-token" />);
  expect(screen.getByRole("link", { name: "Open your memories album" })).toHaveAttribute("href", "/album/explorers-token");
});

it("omits 'Shared' for a unique rank", () => {
  render(<FinishScreen state={makeState({ status: "finished", phase: "results", clock: null, task: null, results: { ...results, rank: 1, shared_rank: false } })} frame={frame} />);
  expect(screen.getByText("1st place")).toBeInTheDocument();
});
