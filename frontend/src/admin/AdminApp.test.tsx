import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AdminApp } from "./AdminApp";
import { adminApi } from "./api";

vi.mock("./api", () => ({
  adminApi: {
    authProvider: vi.fn(),
    requestMagicLink: vi.fn(),
    seedError: vi.fn().mockResolvedValue({ error: null }),
    landmarks: vi.fn().mockResolvedValue([]),
    games: vi.fn().mockResolvedValue([]),
    teams: vi.fn().mockResolvedValue([]),
    teamAssignments: vi.fn().mockResolvedValue([]),
    listTeamPhotos: vi.fn().mockResolvedValue([]),
  },
}));

describe("AdminApp", () => {
  beforeEach(() => {
    vi.mocked(adminApi.requestMagicLink).mockReset();
    vi.mocked(adminApi.authProvider).mockReset().mockResolvedValue({ provider: "dev" });
  });

  describe("routing", () => {
    it("renders the dashboard for /admin", async () => {
      render(<AdminApp path="/admin" />);
      await waitFor(() => expect(adminApi.seedError).toHaveBeenCalled());
      expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
      expect(screen.getByRole("navigation", { name: "Admin navigation" })).toBeInTheDocument();
    });

    it("renders the dashboard for /admin/dashboard", async () => {
      render(<AdminApp path="/admin/dashboard" />);
      await waitFor(() => expect(adminApi.seedError).toHaveBeenCalled());
      expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    });

    it("renders the login screen for /admin/login", async () => {
      render(<AdminApp path="/admin/login" />);
      expect(screen.getByRole("heading", { name: "Admin sign-in" })).toBeInTheDocument();
      expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    });

    it("highlights the active navigation link", async () => {
      render(<AdminApp path="/admin/teams" />);
      await waitFor(() => expect(adminApi.teams).toHaveBeenCalled());
      expect(screen.getByRole("link", { name: "Teams" })).toHaveClass("active");
    });

    it("shows a not-found page for unknown admin routes", () => {
      render(<AdminApp path="/admin/unknown" />);
      expect(screen.getByText("Admin page not found")).toBeInTheDocument();
    });
  });

  describe("lazy loading from App", () => {
    it("renders the admin app for /admin paths via App", async () => {
      render(<App path="/admin" />);
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
      });
    });

    it("skips copy-protection event blockers inside /admin", async () => {
      render(<App path="/admin/some-page" />);
      await waitFor(() => screen.getByRole("navigation"));
      const event = new Event("copy", { bubbles: true, cancelable: true });
      document.body.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(false);
    });
  });

  describe("magic link login", () => {
    it("requests a magic link and displays the returned URL", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.requestMagicLink).mockResolvedValueOnce({
        url: "http://test.local/api/admin/auth/magic/verify?token=abc&email=a%40b.c",
      });

      render(<AdminApp path="/admin/login" />);
      await user.type(await screen.findByLabelText("Email"), "a@b.c");
      await user.click(screen.getByRole("button", { name: "Request magic link" }));

      await waitFor(() => {
        expect(
          screen.getByText("http://test.local/api/admin/auth/magic/verify?token=abc&email=a%40b.c"),
        ).toBeInTheDocument();
      });
      expect(adminApi.requestMagicLink).toHaveBeenCalledWith("a@b.c");
    });
  });

  describe("Entra login", () => {
    it("offers Microsoft sign-in instead of the magic link form", async () => {
      vi.mocked(adminApi.authProvider).mockResolvedValueOnce({ provider: "entra" });

      render(<AdminApp path="/admin/login" />);

      const link = await screen.findByRole("link", { name: "Sign in with Microsoft" });
      expect(link).toHaveAttribute("href", "/api/admin/auth/login");
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
      expect(adminApi.requestMagicLink).not.toHaveBeenCalled();
    });

    it("shows an error when the provider cannot be loaded", async () => {
      vi.mocked(adminApi.authProvider).mockRejectedValueOnce(new Error("offline"));

      render(<AdminApp path="/admin/login" />);

      expect(await screen.findByText(/Could not load the sign-in options/)).toBeInTheDocument();
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    });
  });
});
