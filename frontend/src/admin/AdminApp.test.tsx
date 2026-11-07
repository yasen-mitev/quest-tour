import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AdminApp } from "./AdminApp";
import { adminApi, HttpErrorWithBody } from "./api";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  adminApi: {
    authProvider: vi.fn(),
    passwordLogin: vi.fn(),
    requestMagicLink: vi.fn(),
    seedError: vi.fn().mockResolvedValue({ error: null }),
    landmarks: vi.fn().mockResolvedValue([]),
    games: vi.fn().mockResolvedValue([]),
    teams: vi.fn().mockResolvedValue([]),
    teamAssignments: vi.fn().mockResolvedValue([]),
    listTeamPhotos: vi.fn().mockResolvedValue([]),
    authSettings: vi.fn().mockResolvedValue({
      mode: "password", entra_configured: false, entra_enabled: false, session_provider: "password",
      email: "boss@example.com",
    }),
    listAdmins: vi.fn().mockResolvedValue([]),
  },
}));

describe("AdminApp", () => {
  beforeEach(() => {
    vi.mocked(adminApi.requestMagicLink).mockReset();
    vi.mocked(adminApi.passwordLogin).mockReset();
    vi.mocked(adminApi.authProvider).mockReset().mockResolvedValue({
      provider: "password",
      methods: { password: true, entra: false, dev: false },
    });
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

    it("renders the Administrators screen for /admin/administrators", async () => {
      render(<AdminApp path="/admin/administrators" />);
      expect(await screen.findByRole("heading", { level: 1, name: "Administrators" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Administrators" })).toHaveClass("active");
    });

    it("no longer serves the old /admin/settings path", () => {
      render(<AdminApp path="/admin/settings" />);
      expect(screen.getByText("Admin page not found")).toBeInTheDocument();
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

  describe("password login", () => {
    const fillAndSubmit = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.type(await screen.findByLabelText("Email"), "a@b.c");
      await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
      await user.click(screen.getByRole("button", { name: "Sign in" }));
    };

    it("submits the email and password", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.passwordLogin).mockResolvedValueOnce({ ok: true });

      render(<AdminApp path="/admin/login" />);
      await fillAndSubmit(user);

      await waitFor(() =>
        expect(adminApi.passwordLogin).toHaveBeenCalledWith("a@b.c", "hunter2hunter2"),
      );
    });

    it("shows an error for invalid credentials", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.passwordLogin).mockRejectedValueOnce(
        new HttpErrorWithBody(400, { detail: "invalid email or password" }),
      );

      render(<AdminApp path="/admin/login" />);
      await fillAndSubmit(user);

      expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
    });

    it("shows a rate-limit message on 429", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.passwordLogin).mockRejectedValueOnce(new HttpErrorWithBody(429, {}));

      render(<AdminApp path="/admin/login" />);
      await fillAndSubmit(user);

      expect(
        await screen.findByText("Too many attempts. Try again in a few minutes."),
      ).toBeInTheDocument();
    });

    it("hides the Microsoft link when entra is not available", async () => {
      render(<AdminApp path="/admin/login" />);
      await screen.findByLabelText("Password");
      expect(screen.queryByRole("link", { name: "Sign in with Microsoft" })).not.toBeInTheDocument();
    });
  });

  describe("magic link login", () => {
    it("requests a magic link and displays the returned URL", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.authProvider).mockResolvedValueOnce({
        provider: "dev",
        methods: { password: false, entra: false, dev: true },
      });
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
    it("offers Microsoft sign-in next to the password form", async () => {
      vi.mocked(adminApi.authProvider).mockResolvedValueOnce({
        provider: "entra",
        methods: { password: true, entra: true, dev: false },
      });

      render(<AdminApp path="/admin/login" />);

      const link = await screen.findByRole("link", { name: "Sign in with Microsoft" });
      expect(link).toHaveAttribute("href", "/api/admin/auth/login");
      expect(link).toHaveClass("qc-btn--secondary");
      expect(screen.getByLabelText("Email")).toBeInTheDocument();
      expect(screen.getByLabelText("Password")).toBeInTheDocument();
      expect(adminApi.requestMagicLink).not.toHaveBeenCalled();
    });

    it("makes Microsoft sign-in primary when it is the only method", async () => {
      vi.mocked(adminApi.authProvider).mockResolvedValueOnce({
        provider: "entra",
        methods: { password: false, entra: true, dev: false },
      });

      render(<AdminApp path="/admin/login" />);

      const link = await screen.findByRole("link", { name: "Sign in with Microsoft" });
      expect(link).toHaveClass("qc-btn--primary");
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    });

    it("shows an error when the provider cannot be loaded", async () => {
      vi.mocked(adminApi.authProvider).mockRejectedValueOnce(new Error("offline"));

      render(<AdminApp path="/admin/login" />);

      expect(await screen.findByText(/Could not load the sign-in options/)).toBeInTheDocument();
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    });
  });
});
