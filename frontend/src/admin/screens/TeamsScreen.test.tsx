import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../api";
import type { AssignmentOut, Game, Team } from "../types";
import { TeamsScreen } from "./TeamsScreen";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: {
    teams: vi.fn(),
    games: vi.fn(),
    teamAssignments: vi.fn(),
    createTeam: vi.fn(),
    updateTeam: vi.fn(),
    updateTeamAssignments: vi.fn(),
    reissueToken: vi.fn(),
    deleteTeam: vi.fn(),
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
  time_zone: "Europe/Sofia",
  max_duration_minutes: 120,
  reveal: { attempts: 5, minutes: 20, penalty_minutes: 30 },
  requestable: false,
  updated_at: "2024-01-01T00:00:00Z",
  task_landmark_ids: [],
};

const assignment: AssignmentOut = {
  id: 100,
  game_id: 10,
  game_name: "City Tour",
  valid_from: "2024-01-01T10:00:00+00:00",
  valid_until: "2024-01-01T12:00:00+00:00",
  exit_message: "Goodbye",
  token_issued: true,
  issued_at: "2024-01-01T09:00:00+00:00",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("TeamsScreen", () => {
  beforeEach(() => {
    vi.mocked(adminApi.teams).mockResolvedValue([team]);
    vi.mocked(adminApi.games).mockResolvedValue([game]);
    vi.mocked(adminApi.teamAssignments).mockResolvedValue([assignment]);
    vi.mocked(adminApi.createTeam).mockReset();
    vi.mocked(adminApi.updateTeam).mockReset();
    vi.mocked(adminApi.updateTeamAssignments).mockReset();
    vi.mocked(adminApi.reissueToken).mockReset();
    vi.mocked(adminApi.deleteTeam).mockReset();
  });

  it("lists teams", async () => {
    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => {
      expect(screen.getByText("Team Alpha")).toBeInTheDocument();
    });
    expect(screen.getByText("(alpha)")).toBeInTheDocument();
  });

  it("creates a team", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.createTeam).mockResolvedValueOnce(team);

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "New team" }));
    await user.type(screen.getByLabelText("Key"), "beta");
    await user.type(screen.getByLabelText("Name"), "Team Beta");
    await user.type(screen.getByLabelText("Participants"), "3");
    await user.click(screen.getByRole("button", { name: "Create team" }));

    await waitFor(() => {
      expect(adminApi.createTeam).toHaveBeenCalled();
    });
    const args = vi.mocked(adminApi.createTeam).mock.calls[0];
    expect(args[0].key).toBe("beta");
    expect(args[0].participants).toBe(3);
  });

  it("updates assignments", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateTeamAssignments).mockResolvedValueOnce([]);

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Assignments"));

    const until = screen.getAllByLabelText("Valid until")[0];
    await user.clear(until);
    await user.type(until, "2024-01-01T14:00");

    await user.click(screen.getByRole("button", { name: "Save assignments" }));

    await waitFor(() => {
      expect(adminApi.updateTeamAssignments).toHaveBeenCalledWith(
        1,
        expect.arrayContaining([
          expect.objectContaining({ game_id: 10, valid_until: "2024-01-01T14:00" }),
        ]),
        team.updated_at,
      );
    });
  });

  it("updates a team with seen_at", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateTeam).mockResolvedValueOnce(team);

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Updated Team");
    await user.click(screen.getByRole("button", { name: "Update team" }));

    await waitFor(() => {
      expect(adminApi.updateTeam).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ name: "Updated Team", seen_at: "2024-01-01T00:00:00Z" }),
      );
    });
  });

  it("displays newly revealed assignment tokens after saving", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateTeamAssignments).mockResolvedValueOnce([
      { assignment_id: 100, token: "new-token-123", url: "http://test/play/new-token-123" },
    ]);

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Assignments"));

    const until = screen.getAllByLabelText("Valid until")[0];
    await user.clear(until);
    await user.type(until, "2024-01-01T14:00");
    await user.click(screen.getByRole("button", { name: "Save assignments" }));

    await waitFor(() => {
      expect(screen.getByText(/new-token-123/)).toBeInTheDocument();
    });
  });

  it("refreshes editing updated_at after saving assignments", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateTeamAssignments).mockResolvedValueOnce([]);
    vi.mocked(adminApi.updateTeam).mockResolvedValueOnce(team);
    vi.mocked(adminApi.teams)
      .mockResolvedValueOnce([team])
      .mockResolvedValueOnce([{ ...team, updated_at: "2024-02-01T00:00:00Z" }]);

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Assignments"));

    const until = screen.getAllByLabelText("Valid until")[0];
    await user.clear(until);
    await user.type(until, "2024-01-01T14:00");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save assignments" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Save assignments" }));
    await waitFor(() => expect(adminApi.updateTeamAssignments).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: "Update team" })).toBeEnabled());

    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Updated Team");
    await user.click(screen.getByRole("button", { name: "Update team" }));

    await waitFor(() => {
      expect(adminApi.updateTeam).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ seen_at: "2024-02-01T00:00:00Z" }),
      );
    });
  });

  it("reissues a token", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.reissueToken).mockResolvedValueOnce({
      assignment_id: 100,
      token: "abc123",
      url: "http://test/play/abc123",
    });

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Assignments"));

    await user.click(screen.getByRole("button", { name: "Reissue token" }));

    await waitFor(() => {
      expect(adminApi.reissueToken).toHaveBeenCalledWith(100);
    });
    expect(screen.getByText(/abc123/)).toBeInTheDocument();
  });

  it("deletes a team after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.deleteTeam).mockResolvedValueOnce({ deleted: true });

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const confirmButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(adminApi.deleteTeam).toHaveBeenCalledWith(1);
    });
  });

  it("shows validation errors", async () => {
    const user = userEvent.setup();
    const { HttpErrorWithBody } = await import("../api");
    vi.mocked(adminApi.createTeam).mockRejectedValueOnce(
      new HttpErrorWithBody(422, { errors: [{ field: "key", message: "already exists" }] }),
    );

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "New team" }));
    await user.type(screen.getByLabelText("Key"), "dup");
    await user.type(screen.getByLabelText("Name"), "Dup");
    await user.click(screen.getByRole("button", { name: "Create team" }));

    expect(await screen.findByText("already exists")).toBeInTheDocument();
    expect(adminApi.createTeam).toHaveBeenCalled();
  });

  it("shows conflict error", async () => {
    const user = userEvent.setup();
    const { HttpErrorWithBody } = await import("../api");
    vi.mocked(adminApi.updateTeam).mockRejectedValueOnce(
      new HttpErrorWithBody(409, { entity: "Team", current: { id: 1, updated_at: "2026-10-07T10:00:00Z" } }),
    );

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Other");
    await user.click(screen.getByRole("button", { name: "Update team" }));

    expect(await screen.findByText(/Another admin edited this team/)).toBeInTheDocument();
  });

  it("shows server reference on server error", async () => {
    const user = userEvent.setup();
    const { HttpErrorWithBody } = await import("../api");
    vi.mocked(adminApi.updateTeam).mockRejectedValueOnce(
      new HttpErrorWithBody(500, { reference: "ref-456" }),
    );

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Other");
    await user.click(screen.getByRole("button", { name: "Update team" }));

    expect(await screen.findByText(/ref-456/)).toBeInTheDocument();
  });

  it("warns before closing when assignments are dirty", async () => {
    const user = userEvent.setup();
    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Assignments"));

    const until = screen.getAllByLabelText("Valid until")[0];
    await user.clear(until);
    await user.type(until, "2024-01-01T14:00");

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("confirms discarding assignment changes on cancel", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<TeamsScreen subPath="teams" />);
    await waitFor(() => screen.getByText("Team Alpha"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Assignments"));

    const until = screen.getAllByLabelText("Valid until")[0];
    await user.clear(until);
    await user.type(until, "2024-01-01T14:00");

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(window.confirm).toHaveBeenCalledWith("Discard unsaved changes?");
    expect(screen.getByRole("button", { name: "Save assignments" })).toBeInTheDocument();
  });
});
