import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../api";
import { Dashboard } from "./Dashboard";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: {
    seedError: vi.fn(),
    gameRequests: vi.fn(),
  },
}));

describe("Dashboard", () => {
  beforeEach(() => {
    vi.mocked(adminApi.seedError).mockReset();
    vi.mocked(adminApi.gameRequests).mockReset().mockResolvedValue([]);
  });

  it("shows seed error banner when present", async () => {
    vi.mocked(adminApi.seedError).mockResolvedValueOnce({ error: "Missing fixture" });
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/Missing fixture/)).toBeInTheDocument();
    });
  });

  it("shows navigation when there is no seed error", async () => {
    vi.mocked(adminApi.seedError).mockResolvedValueOnce({ error: null });
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Landmarks" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Games" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Teams" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Photos" })).toBeInTheDocument();
  });

  it("shows the number of pending requests as a card linking to Requests", async () => {
    vi.mocked(adminApi.seedError).mockResolvedValueOnce({ error: null });
    vi.mocked(adminApi.gameRequests).mockResolvedValueOnce([
      { id: 1, created_at: "2026-11-01T09:00:00Z", contact_name: "A", game_id: 1, game_name: "G", play_date: "2026-11-20", team_count: 1, status: "pending" },
      { id: 2, created_at: "2026-11-01T10:00:00Z", contact_name: "B", game_id: 1, game_name: "G", play_date: "2026-11-21", team_count: 2, status: "pending" },
    ]);
    render(<Dashboard />);

    const card = await screen.findByRole("link", { name: "Pending requests: 2" });
    expect(card).toHaveAttribute("href", "/admin/requests");
    expect(adminApi.gameRequests).toHaveBeenCalledWith("pending");
  });

  it("leaves the pending requests card out when the count cannot be loaded", async () => {
    vi.mocked(adminApi.seedError).mockResolvedValueOnce({ error: null });
    vi.mocked(adminApi.gameRequests).mockRejectedValueOnce(new Error("offline"));
    render(<Dashboard />);

    await screen.findByRole("link", { name: "Landmarks" });
    expect(screen.queryByRole("link", { name: /Pending requests/ })).not.toBeInTheDocument();
  });
});
