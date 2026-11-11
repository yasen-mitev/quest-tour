import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi, HttpErrorWithBody } from "../api";
import type { Game, GameRequestDetail, GameRequestListItem } from "../types";
import { RequestsScreen } from "./RequestsScreen";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: {
    games: vi.fn(),
    gameRequests: vi.fn(),
    gameRequest: vi.fn(),
    updateGameRequest: vi.fn(),
    approveGameRequest: vi.fn(),
    rejectGameRequest: vi.fn(),
  },
}));

const game: Game = {
  id: 10,
  key: "city",
  name: "City Tour",
  intro: "Welcome",
  time_zone: "Europe/Sofia",
  max_duration_minutes: 120,
  reveal: { attempts: 5, minutes: 20, penalty_minutes: 30 },
  requestable: true,
  updated_at: "2026-10-01T00:00:00Z",
  task_landmark_ids: [],
};

const nightGame: Game = { ...game, id: 11, key: "night", name: "Night Walk", requestable: false };

const listItem: GameRequestListItem = {
  id: 5,
  created_at: "2026-11-01T09:00:00+00:00",
  contact_name: "Maria Petrova",
  game_id: 10,
  game_name: "City Tour",
  play_date: "2026-11-20",
  team_count: 2,
  status: "pending",
};

// Europe/Sofia is UTC+2 in November: team 1 has the play-date default window, team 2 its own.
const pending: GameRequestDetail = {
  id: 5,
  created_at: "2026-11-01T09:00:00+00:00",
  updated_at: "2026-11-01T09:00:00.123456+00:00",
  status: "pending",
  game_id: 10,
  game_name: "City Tour",
  game_time_zone: "Europe/Sofia",
  play_date: "2026-11-20",
  contact_name: "Maria Petrova",
  contact_email: "maria@example.com",
  contact_phone: "+359 88 123 4567",
  message: "Two school classes",
  exit_message: "Thanks for playing!",
  terms_accepted_at: "2026-11-01T09:00:00+00:00",
  terms_version: "11 October 2026",
  decided_at: null,
  decided_by: null,
  teams: [
    {
      name: "Red Foxes",
      key: "red-foxes",
      participants: 5,
      valid_from: "2026-11-19T22:00:00+00:00",
      valid_until: "2026-11-20T21:59:59+00:00",
      team_id: null,
    },
    {
      name: "Blue Owls",
      key: "blue-owls",
      participants: null,
      valid_from: "2026-11-20T08:00:00+00:00",
      valid_until: "2026-11-20T12:00:00+00:00",
      team_id: null,
    },
  ],
};

const approved: GameRequestDetail = {
  ...pending,
  updated_at: "2026-11-02T10:00:00+00:00",
  status: "approved",
  decided_at: "2026-11-02T10:00:00+00:00",
  decided_by: "boss@example.com",
  teams: pending.teams.map((t, i) => ({ ...t, team_id: 77 + i })),
};

const team = (n: number) => within(screen.getByRole("group", { name: `Team ${n}` }));

async function openDetail() {
  render(<RequestsScreen subPath="requests/5" />);
  await screen.findByRole("heading", { name: "Request from Maria Petrova" });
}

describe("RequestsScreen", () => {
  beforeEach(() => {
    vi.mocked(adminApi.games).mockReset().mockResolvedValue([game, nightGame]);
    vi.mocked(adminApi.gameRequests).mockReset().mockResolvedValue([listItem]);
    vi.mocked(adminApi.gameRequest).mockReset().mockResolvedValue(pending);
    vi.mocked(adminApi.updateGameRequest).mockReset();
    vi.mocked(adminApi.approveGameRequest).mockReset();
    vi.mocked(adminApi.rejectGameRequest).mockReset();
  });

  describe("list", () => {
    it("shows pending requests by default and filters by status", async () => {
      const user = userEvent.setup();
      render(<RequestsScreen subPath="requests" />);

      expect(await screen.findByText("Maria Petrova")).toBeInTheDocument();
      expect(adminApi.gameRequests).toHaveBeenCalledWith("pending");
      expect(screen.getByText(/City Tour · 2026-11-20 · 2 teams/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/admin/requests/5");

      vi.mocked(adminApi.gameRequests).mockResolvedValueOnce([
        { ...listItem, id: 6, contact_name: "Ivan Ivanov", game_id: null, game_name: null, status: "rejected" },
      ]);
      await user.selectOptions(screen.getByLabelText("Status"), "all");

      expect(await screen.findByText("Ivan Ivanov")).toBeInTheDocument();
      expect(adminApi.gameRequests).toHaveBeenLastCalledWith("all");
      expect(screen.getByText(/Game removed/)).toBeInTheDocument();
      expect(screen.queryByText("Maria Petrova")).not.toBeInTheDocument();
    });

    it("says when there are no requests", async () => {
      vi.mocked(adminApi.gameRequests).mockResolvedValueOnce([]);
      render(<RequestsScreen subPath="requests" />);
      expect(await screen.findByText("No pending requests.")).toBeInTheDocument();
    });
  });

  describe("detail", () => {
    it("shows the contact, the consent time and version, and the team windows in the game's time zone", async () => {
      await openDetail();

      expect(adminApi.gameRequest).toHaveBeenCalledWith(5);
      expect(screen.getByText("maria@example.com")).toBeInTheDocument();
      expect(screen.getByText("+359 88 123 4567")).toBeInTheDocument();
      expect(screen.getByText("Two school classes")).toBeInTheDocument();
      expect(
        screen.getByText(`${new Date(pending.terms_accepted_at).toLocaleString()}, version 11 October 2026`),
      ).toBeInTheDocument();

      expect(screen.getByLabelText("Game")).toHaveValue("10");
      expect(screen.getByLabelText("Exit message")).toHaveValue("Thanks for playing!");
      expect(team(1).getByLabelText("Name")).toHaveValue("Red Foxes");
      expect(team(1).getByLabelText("Valid from")).toHaveValue("2026-11-20T00:00");
      // Browsers report "23:59:59"; jsdom normalizes it to "23:59:59.000".
      expect((team(1).getByLabelText("Valid until") as HTMLInputElement).value).toMatch(
        /^2026-11-20T23:59:59(\.000)?$/,
      );
      expect(team(2).getByLabelText("Participants")).toHaveValue(null);
      expect(team(2).getByLabelText("Valid from")).toHaveValue("2026-11-20T10:00");
    });

    it("saves edits, sending play-date default windows as null", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.updateGameRequest).mockResolvedValueOnce({
        ...pending,
        updated_at: "2026-11-01T10:00:00+00:00",
      });
      await openDetail();

      await user.selectOptions(screen.getByLabelText("Game"), "11");
      await user.clear(screen.getByLabelText("Exit message"));
      await user.type(screen.getByLabelText("Exit message"), "Bye");
      await user.clear(team(2).getByLabelText("Key"));
      await user.type(team(2).getByLabelText("Key"), "night-owls");
      await user.type(team(2).getByLabelText("Participants"), "3");
      await user.click(screen.getByRole("button", { name: "Save changes" }));

      await waitFor(() => expect(adminApi.updateGameRequest).toHaveBeenCalled());
      expect(adminApi.updateGameRequest).toHaveBeenCalledWith(5, {
        game_id: 11,
        exit_message: "Bye",
        teams: [
          { name: "Red Foxes", key: "red-foxes", participants: 5, valid_from: null, valid_until: null },
          {
            name: "Blue Owls",
            key: "night-owls",
            participants: 3,
            valid_from: "2026-11-20T10:00",
            valid_until: "2026-11-20T14:00",
          },
        ],
        seen_at: pending.updated_at,
      });
    });

    it("keeps approve and reject off while there are unsaved changes", async () => {
      const user = userEvent.setup();
      await openDetail();

      await user.type(team(1).getByLabelText("Name"), " Jr");

      expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
      expect(screen.getByText("Save or discard your changes before deciding.")).toBeInTheDocument();
    });

    it("shows save errors on the team row", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.updateGameRequest).mockRejectedValueOnce(
        new HttpErrorWithBody(422, {
          errors: [{ field: "teams.0.valid_until", message: "valid_until must be after valid_from" }],
        }),
      );
      await openDetail();

      await user.type(team(1).getByLabelText("Name"), " Jr");
      await user.click(screen.getByRole("button", { name: "Save changes" }));

      expect(await team(1).findByText("valid_until must be after valid_from")).toBeInTheDocument();
      expect(team(1).getByLabelText("Valid until")).toHaveAttribute("aria-invalid", "true");
    });

    it("approves after confirmation and shows the play links once", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.approveGameRequest).mockResolvedValueOnce([
        { assignment_id: 1, token: "tok-a", url: "https://app.test/play/tok-a" },
        { assignment_id: 2, token: "tok-b", url: "https://app.test/play/tok-b" },
      ]);
      vi.mocked(adminApi.gameRequest).mockResolvedValueOnce(pending).mockResolvedValueOnce(approved);
      await openDetail();

      await user.click(screen.getByRole("button", { name: "Approve" }));
      const dialog = screen.getByRole("dialog", { name: "Approve request" });
      expect(dialog).toHaveTextContent("2 teams");
      await user.click(within(dialog).getByRole("button", { name: "Approve" }));

      await waitFor(() => expect(adminApi.approveGameRequest).toHaveBeenCalledWith(5, pending.updated_at));
      const links = await screen.findByRole("region", { name: "Play links" });
      expect(within(links).getByText("Red Foxes")).toBeInTheDocument();
      expect(within(links).getByRole("link", { name: "https://app.test/play/tok-b" })).toHaveAttribute(
        "href",
        "https://app.test/play/tok-b",
      );
      await user.click(within(links).getAllByRole("button", { name: "Copy" })[0]);
      await expect(navigator.clipboard.readText()).resolves.toBe("https://app.test/play/tok-a");

      expect(screen.getByText(/Approved by boss@example.com/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    });

    it("shows an approval clash on the clashing team row and stays editable", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.approveGameRequest).mockRejectedValueOnce(
        new HttpErrorWithBody(422, {
          errors: [{ field: "teams.1.key", message: "A team with this key already exists" }],
        }),
      );
      await openDetail();

      await user.click(screen.getByRole("button", { name: "Approve" }));
      await user.click(
        within(screen.getByRole("dialog", { name: "Approve request" })).getByRole("button", { name: "Approve" }),
      );

      expect(await team(2).findByText("A team with this key already exists")).toBeInTheDocument();
      expect(team(2).getByLabelText("Key")).toHaveAttribute("aria-invalid", "true");
      expect(team(1).queryByText("A team with this key already exists")).not.toBeInTheDocument();
      expect(team(2).getByLabelText("Key")).toBeEnabled();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("shows a missing game on the game field", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.approveGameRequest).mockRejectedValueOnce(
        new HttpErrorWithBody(422, { errors: [{ field: "game_id", message: "Choose a game before approving" }] }),
      );
      await openDetail();

      await user.click(screen.getByRole("button", { name: "Approve" }));
      await user.click(
        within(screen.getByRole("dialog", { name: "Approve request" })).getByRole("button", { name: "Approve" }),
      );

      expect(await screen.findByText("Choose a game before approving")).toBeInTheDocument();
      expect(screen.getByLabelText("Game")).toHaveAttribute("aria-invalid", "true");
    });

    it("rejects after confirmation and becomes read-only", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.rejectGameRequest).mockResolvedValueOnce({
        ...pending,
        status: "rejected",
        decided_at: "2026-11-02T10:00:00+00:00",
        decided_by: "boss@example.com",
      });
      await openDetail();

      await user.click(screen.getByRole("button", { name: "Reject" }));
      await user.click(
        within(screen.getByRole("dialog", { name: "Reject request" })).getByRole("button", { name: "Reject" }),
      );

      await waitFor(() => expect(adminApi.rejectGameRequest).toHaveBeenCalledWith(5, pending.updated_at));
      expect(await screen.findByText(/Rejected by boss@example.com/)).toBeInTheDocument();
      expect(screen.getByLabelText("Game")).toBeDisabled();
      expect(team(1).getByLabelText("Key")).toBeDisabled();
      expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    });

    it("reloads and switches to read-only when another admin decided first (409)", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.approveGameRequest).mockRejectedValueOnce(
        new HttpErrorWithBody(409, { entity: "GameRequest", current: approved }),
      );
      vi.mocked(adminApi.gameRequest).mockResolvedValueOnce(pending).mockResolvedValueOnce(approved);
      await openDetail();

      await user.click(screen.getByRole("button", { name: "Approve" }));
      await user.click(
        within(screen.getByRole("dialog", { name: "Approve request" })).getByRole("button", { name: "Approve" }),
      );

      expect(await screen.findByText(/Another admin has already approved this request/)).toBeInTheDocument();
      expect(adminApi.gameRequest).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
      expect(team(1).getByLabelText("Name")).toBeDisabled();
    });

    it("shows a decided request read-only, with links to the created teams", async () => {
      vi.mocked(adminApi.gameRequest).mockResolvedValue(approved);
      await openDetail();

      expect(screen.getByText(/Approved by boss@example.com/)).toBeInTheDocument();
      expect(screen.getByLabelText("Game")).toBeDisabled();
      expect(screen.getByLabelText("Exit message")).toBeDisabled();
      for (const n of [1, 2]) {
        for (const label of ["Name", "Key", "Participants", "Valid from", "Valid until"]) {
          expect(team(n).getByLabelText(label)).toBeDisabled();
        }
      }
      expect(team(1).getByRole("link", { name: "Open team" })).toHaveAttribute("href", "/admin/teams/77");
      for (const name of ["Save changes", "Approve", "Reject", "Add team", "Remove"]) {
        expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
      }
    });
  });
});
