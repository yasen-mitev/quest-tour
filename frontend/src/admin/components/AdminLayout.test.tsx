import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsentBanner } from "../../components/ConsentBanner";
import { APP_VERSION, versionLabel } from "../../lib/version";
import { AdminLayout, REQUESTS_CHANGED } from "./AdminLayout";
import { adminApi } from "../api";

vi.mock("../api", () => ({
  adminApi: {
    logout: vi.fn(),
    gameRequests: vi.fn(),
  },
}));

describe("AdminLayout", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(adminApi.logout).mockReset();
    vi.mocked(adminApi.gameRequests).mockReset().mockResolvedValue([]);
    vi.stubGlobal("location", { href: "" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a Logout button", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
  });

  it("links to the Administrators screen", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    expect(screen.getByRole("link", { name: "Administrators" })).toHaveAttribute("href", "/admin/administrators");
  });

  it("lists Requests right after Dashboard", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links.slice(0, 2)).toEqual(["/admin/dashboard", "/admin/requests"]);
  });

  it("badges Requests with the number of pending requests", async () => {
    vi.mocked(adminApi.gameRequests).mockResolvedValueOnce([
      { id: 1, created_at: "2026-11-01T09:00:00Z", contact_name: "A", game_id: 1, game_name: "G", play_date: "2026-11-20", team_count: 1, status: "pending" },
      { id: 2, created_at: "2026-11-01T10:00:00Z", contact_name: "B", game_id: 1, game_name: "G", play_date: "2026-11-21", team_count: 2, status: "pending" },
      { id: 3, created_at: "2026-11-01T11:00:00Z", contact_name: "C", game_id: 1, game_name: "G", play_date: "2026-11-22", team_count: 1, status: "pending" },
    ]);
    render(<AdminLayout active="dashboard">Content</AdminLayout>);

    expect(await screen.findByRole("link", { name: "Requests (3 pending)" })).toHaveAttribute("href", "/admin/requests");
    expect(adminApi.gameRequests).toHaveBeenCalledWith("pending");
  });

  it("shows no badge when nothing is pending", async () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    await waitFor(() => expect(adminApi.gameRequests).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: "Requests" })).toBeInTheDocument();
  });

  it("refreshes the badge when a request is decided", async () => {
    vi.mocked(adminApi.gameRequests)
      .mockResolvedValueOnce([
        { id: 1, created_at: "2026-11-01T09:00:00Z", contact_name: "A", game_id: 1, game_name: "G", play_date: "2026-11-20", team_count: 1, status: "pending" },
      ])
      .mockResolvedValueOnce([]);
    render(<AdminLayout active="requests">Content</AdminLayout>);
    await screen.findByRole("link", { name: "Requests (1 pending)" });

    window.dispatchEvent(new Event(REQUESTS_CHANGED));

    expect(await screen.findByRole("link", { name: "Requests" })).toHaveClass("active");
    expect(adminApi.gameRequests).toHaveBeenCalledTimes(2);
  });

  it("shows the running version at the foot of the sidebar (issue #29)", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    expect(screen.getByRole("contentinfo")).toHaveTextContent(versionLabel(APP_VERSION));
  });

  it("offers a Cookies link at the foot of the sidebar, above the version footer", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    const link = screen.getByRole("button", { name: "Cookies" });
    expect(screen.getByRole("navigation", { name: "Admin navigation" }).contains(link)).toBe(true);
    const version = screen.getByRole("contentinfo");
    expect(version.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  });

  it("offers the legal and contact pages at the foot of the sidebar", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy?from=admin");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms?from=admin");
    expect(screen.getByRole("link", { name: "Contact" })).toHaveAttribute("href", "/contact?from=admin");
  });

  it("re-opens the consent banner from the Cookie settings link", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      "questtour-consent",
      JSON.stringify({ choice: "declined", at: "2026-10-09T10:00:00.000Z" }),
    );
    render(
      <>
        <ConsentBanner app="admin" />
        <AdminLayout active="dashboard">Content</AdminLayout>
      </>,
    );
    expect(screen.queryByRole("dialog", { name: "About cookies" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cookies" }));
    expect(screen.getByRole("dialog", { name: "About cookies" })).toBeInTheDocument();
  });

  it("calls logout and redirects to login when Logout is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.logout).mockResolvedValueOnce({ ok: true });

    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    await user.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => {
      expect(adminApi.logout).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(window.location.href).toBe("/admin/login");
    });
  });
});
