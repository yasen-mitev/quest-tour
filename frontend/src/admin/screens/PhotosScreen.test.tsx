import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../api";
import type { Game, Team, TeamPhotoOut } from "../types";
import { PhotosScreen } from "./PhotosScreen";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: {
    teams: vi.fn(),
    games: vi.fn(),
    listTeamPhotos: vi.fn(),
    deleteTeamPhoto: vi.fn(),
  },
}));

const team: Team = {
  id: 1,
  key: "alpha",
  name: "Team Alpha",
  participants: 4,
  updated_at: "2024-01-01T00:00:00Z",
};

const game: Game = {
  id: 10,
  key: "city",
  name: "City Tour",
  intro: "Welcome",
  time_zone: "UTC",
  max_duration_minutes: 120,
  reveal: { attempts: 5, minutes: 20, penalty_minutes: 30 },
  requestable: false,
  updated_at: "2024-01-01T00:00:00Z",
  task_landmark_ids: [],
};

const photo: TeamPhotoOut = {
  id: 100,
  team_name: "Team Alpha",
  game_name: "City Tour",
  uploaded_at: "2024-01-01T12:00:00Z",
  url: "http://test/photos/100",
};

describe("PhotosScreen", () => {
  beforeEach(() => {
    vi.mocked(adminApi.teams).mockResolvedValue([team]);
    vi.mocked(adminApi.games).mockResolvedValue([game]);
    vi.mocked(adminApi.listTeamPhotos).mockResolvedValue([photo]);
    vi.mocked(adminApi.deleteTeamPhoto).mockReset();
  });

  it("lists photos", async () => {
    render(<PhotosScreen />);
    await waitFor(() => {
      expect(screen.getByText("View photo")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Team Alpha").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("City Tour").length).toBeGreaterThanOrEqual(1);
  });

  it("filters by team and game", async () => {
    const user = userEvent.setup();
    render(<PhotosScreen />);
    await waitFor(() => screen.getByText("View photo"));

    await user.selectOptions(screen.getByLabelText("Team"), "1");
    await user.selectOptions(screen.getByLabelText("Game"), "10");
    await user.click(screen.getByRole("button", { name: "Filter" }));

    await waitFor(() => {
      expect(adminApi.listTeamPhotos).toHaveBeenLastCalledWith(1, 10);
    });
  });

  it("deletes a photo after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.deleteTeamPhoto).mockResolvedValueOnce({ deleted: true });

    render(<PhotosScreen />);
    await waitFor(() => screen.getByText("View photo"));

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const confirmButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(adminApi.deleteTeamPhoto).toHaveBeenCalledWith(100);
    });
  });
});
