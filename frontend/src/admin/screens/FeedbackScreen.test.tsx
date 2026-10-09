import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../api";
import { FeedbackScreen } from "./FeedbackScreen";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: { feedback: vi.fn() },
}));

describe("FeedbackScreen", () => {
  beforeEach(() => vi.mocked(adminApi.feedback).mockReset());

  it("lists each riddle's average stars and the teams' comments", async () => {
    vi.mocked(adminApi.feedback).mockResolvedValue({
      riddles: [
        { landmark_id: 1, landmark_name: "Lily Pond", average: 4.5, count: 8 },
        { landmark_id: 2, landmark_name: "Eagles' Bridge", average: 2.75, count: 4 },
      ],
      comments: [
        { id: 9, team_name: "The Explorers", game_name: "Sofia Old Town Quest", submitted_at: "2026-10-03T10:40:00Z", text: "Loved the bridge riddle." },
      ],
    });
    render(<FeedbackScreen />);
    const riddles = await screen.findByRole("list", { name: "Riddle ratings" });
    const rows = within(riddles).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Lily Pond");
    expect(rows[0]).toHaveTextContent("8 ratings");
    expect(rows[0]).toHaveTextContent("4.5");
    expect(rows[1]).toHaveTextContent("2.8");
    const comments = screen.getByRole("list", { name: "Team comments" });
    expect(comments).toHaveTextContent("The Explorers");
    expect(comments).toHaveTextContent("Loved the bridge riddle.");
  });

  it("says so when nothing has been rated or written yet", async () => {
    vi.mocked(adminApi.feedback).mockResolvedValue({ riddles: [], comments: [] });
    render(<FeedbackScreen />);
    expect(await screen.findByText("No riddle has been rated yet.")).toBeInTheDocument();
    expect(screen.getByText("No team has left a comment yet.")).toBeInTheDocument();
  });
});
