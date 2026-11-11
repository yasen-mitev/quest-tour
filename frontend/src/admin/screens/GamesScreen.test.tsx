import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../api";
import type { Game, Landmark } from "../types";
import { GamesScreen } from "./GamesScreen";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: {
    games: vi.fn(),
    landmarks: vi.fn(),
    createGame: vi.fn(),
    updateGame: vi.fn(),
    updateGameTasks: vi.fn(),
    deleteGame: vi.fn(),
  },
}));

const game: Game = {
  id: 1,
  key: "city",
  name: "City Tour",
  intro: "Welcome",
  time_zone: "Europe/Sofia",
  max_duration_minutes: 120,
  reveal: { attempts: 5, minutes: 20, penalty_minutes: 30 },
  requestable: false,
  updated_at: "2024-01-01T00:00:00Z",
  task_landmark_ids: [1],
};

const landmarks: Landmark[] = [
  {
    id: 1,
    key: "a",
    name: "Landmark A",
    name_i18n: null,
    task: "task a",
    task_i18n: null,
    accepted_answers: ["a"],
    hint1: null,
    hint1_i18n: null,
    hint2: null,
    hint2_i18n: null,
    tourist_info: "info a",
    tourist_info_i18n: null,
    coordinates: null,
    task_image_url: null,
    info_image_url: null,
    updated_at: "2024-01-01T00:00:00Z",
  },
  {
    id: 2,
    key: "b",
    name: "Landmark B",
    name_i18n: null,
    task: "task b",
    task_i18n: null,
    accepted_answers: ["b"],
    hint1: null,
    hint1_i18n: null,
    hint2: null,
    hint2_i18n: null,
    tourist_info: "info b",
    tourist_info_i18n: null,
    coordinates: null,
    task_image_url: null,
    info_image_url: null,
    updated_at: "2024-01-01T00:00:00Z",
  },
];

describe("GamesScreen", () => {
  beforeEach(() => {
    vi.mocked(adminApi.games).mockResolvedValue([game]);
    vi.mocked(adminApi.landmarks).mockResolvedValue(landmarks);
    vi.mocked(adminApi.createGame).mockReset();
    vi.mocked(adminApi.updateGame).mockReset();
    vi.mocked(adminApi.updateGameTasks).mockReset();
    vi.mocked(adminApi.deleteGame).mockReset();
  });

  it("lists games", async () => {
    render(<GamesScreen subPath="games" />);
    await waitFor(() => {
      expect(screen.getByText("City Tour")).toBeInTheDocument();
    });
    expect(screen.getByText("(city)")).toBeInTheDocument();
  });

  it("creates a game", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.createGame).mockResolvedValueOnce(game);

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "New game" }));
    await user.type(screen.getByLabelText("Key"), "new-game");
    await user.type(screen.getByLabelText("Name"), "New Game");
    await user.type(screen.getByLabelText("Intro"), "Intro text");
    await user.type(screen.getByLabelText("Time zone"), "UTC");
    await user.clear(screen.getByLabelText("Duration (minutes)"));
    await user.type(screen.getByLabelText("Duration (minutes)"), "90");
    await user.clear(screen.getByLabelText("Reveal attempts"));
    await user.type(screen.getByLabelText("Reveal attempts"), "3");
    await user.click(screen.getByRole("button", { name: "Create game" }));

    await waitFor(() => {
      expect(adminApi.createGame).toHaveBeenCalled();
    });
    const args = vi.mocked(adminApi.createGame).mock.calls[0];
    expect(args[0].key).toBe("new-game");
    expect(args[0].max_duration_minutes).toBe(90);
    expect(args[0].reveal).toEqual({ attempts: 3, minutes: 20, penalty_minutes: 30 });
  });

  it("edits tasks and saves them", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateGameTasks).mockResolvedValueOnce({ ok: true });

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Tasks"));

    await user.click(screen.getByRole("button", { name: "Remove Landmark A" }));
    const select = screen.getByLabelText("Add landmark");
    await user.selectOptions(select, "2");
    await user.click(screen.getByRole("button", { name: "Add landmark" }));

    await user.click(screen.getByRole("button", { name: "Save tasks" }));

    await waitFor(() => {
      expect(adminApi.updateGameTasks).toHaveBeenCalledWith(1, [2], game.updated_at);
    });
  });

  it("updates a game with seen_at", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateGame).mockResolvedValueOnce(game);

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Updated Game");
    await user.click(screen.getByRole("button", { name: "Update game" }));

    await waitFor(() => {
      expect(adminApi.updateGame).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ name: "Updated Game", seen_at: "2024-01-01T00:00:00Z" }),
      );
    });
  });

  it("offers a game on the website's request form with the Requestable checkbox", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateGame).mockResolvedValueOnce({ ...game, requestable: true });

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const checkbox = screen.getByRole("checkbox", { name: "Requestable on the website" });
    expect(checkbox).not.toBeChecked();
    await user.click(checkbox);
    expect(checkbox).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Update game" }));

    await waitFor(() => {
      expect(adminApi.updateGame).toHaveBeenCalledWith(1, expect.objectContaining({ requestable: true }));
    });
  });

  it("shows a requestable game's checkbox ticked and creates new games not requestable", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.games).mockResolvedValue([{ ...game, requestable: true }]);
    vi.mocked(adminApi.createGame).mockResolvedValueOnce(game);

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("checkbox", { name: "Requestable on the website" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "New game" }));
    expect(screen.getByRole("checkbox", { name: "Requestable on the website" })).not.toBeChecked();
    await user.type(screen.getByLabelText("Key"), "new-game");
    await user.type(screen.getByLabelText("Name"), "New Game");
    await user.type(screen.getByLabelText("Intro"), "Intro text");
    await user.click(screen.getByRole("button", { name: "Create game" }));

    await waitFor(() => expect(adminApi.createGame).toHaveBeenCalled());
    expect(vi.mocked(adminApi.createGame).mock.calls[0][0].requestable).toBe(false);
  });

  it("refreshes editing updated_at after saving tasks", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.updateGameTasks).mockResolvedValueOnce({ ok: true });
    vi.mocked(adminApi.updateGame).mockResolvedValueOnce(game);
    vi.mocked(adminApi.games)
      .mockResolvedValueOnce([game])
      .mockResolvedValueOnce([{ ...game, updated_at: "2024-02-01T00:00:00Z" }]);

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Tasks"));

    await user.click(screen.getByRole("button", { name: "Remove Landmark A" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save tasks" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Save tasks" }));
    await waitFor(() => expect(adminApi.updateGameTasks).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: "Update game" })).toBeEnabled());

    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Updated Game");
    await user.click(screen.getByRole("button", { name: "Update game" }));

    await waitFor(() => {
      expect(adminApi.updateGame).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ seen_at: "2024-02-01T00:00:00Z" }),
      );
    });
  });

  it("deletes a game after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.deleteGame).mockResolvedValueOnce({ deleted: true });

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const confirmButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(adminApi.deleteGame).toHaveBeenCalledWith(1);
    });
  });

  it("shows validation errors", async () => {
    const user = userEvent.setup();
    const { HttpErrorWithBody } = await import("../api");
    vi.mocked(adminApi.createGame).mockRejectedValueOnce(
      new HttpErrorWithBody(422, { errors: [{ field: "key", message: "already exists" }] }),
    );

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "New game" }));
    await user.type(screen.getByLabelText("Key"), "dup");
    await user.type(screen.getByLabelText("Name"), "Dup");
    await user.type(screen.getByLabelText("Intro"), "x");
    await user.type(screen.getByLabelText("Time zone"), "UTC");
    await user.click(screen.getByRole("button", { name: "Create game" }));

    expect(await screen.findByText("already exists")).toBeInTheDocument();
    expect(adminApi.createGame).toHaveBeenCalled();
  });

  it("shows conflict error", async () => {
    const user = userEvent.setup();
    const { HttpErrorWithBody } = await import("../api");
    vi.mocked(adminApi.updateGame).mockRejectedValueOnce(
      new HttpErrorWithBody(409, { entity: "Game", current: { id: 1, updated_at: "2026-10-07T10:00:00Z" } }),
    );

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Other");
    await user.click(screen.getByRole("button", { name: "Update game" }));

    expect(await screen.findByText(/Another admin edited this game/)).toBeInTheDocument();
  });

  it("shows server reference on server error", async () => {
    const user = userEvent.setup();
    const { HttpErrorWithBody } = await import("../api");
    vi.mocked(adminApi.updateGame).mockRejectedValueOnce(
      new HttpErrorWithBody(500, { reference: "ref-123" }),
    );

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Other");
    await user.click(screen.getByRole("button", { name: "Update game" }));

    expect(await screen.findByText(/ref-123/)).toBeInTheDocument();
  });

  it("warns before closing when tasks are dirty", async () => {
    const user = userEvent.setup();
    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Tasks"));

    await user.click(screen.getByRole("button", { name: "Remove Landmark A" }));

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("confirms discarding task changes on cancel", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<GamesScreen subPath="games" />);
    await waitFor(() => screen.getByText("City Tour"));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => screen.getByText("Tasks"));

    await user.click(screen.getByRole("button", { name: "Remove Landmark A" }));

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(window.confirm).toHaveBeenCalledWith("Discard unsaved changes?");
    expect(screen.getByRole("button", { name: "Save tasks" })).toBeInTheDocument();
  });
});
