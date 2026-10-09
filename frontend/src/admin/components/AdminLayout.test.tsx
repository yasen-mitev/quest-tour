import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsentBanner } from "../../components/ConsentBanner";
import { APP_VERSION, versionLabel } from "../../lib/version";
import { AdminLayout } from "./AdminLayout";
import { adminApi } from "../api";

vi.mock("../api", () => ({
  adminApi: {
    logout: vi.fn(),
  },
}));

describe("AdminLayout", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(adminApi.logout).mockReset();
    vi.stubGlobal("location", { href: "" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a Logout button", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
  });

  it("shows the running version at the foot of the sidebar (issue #29)", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    expect(screen.getByRole("contentinfo")).toHaveTextContent(versionLabel(APP_VERSION));
  });

  it("offers a Cookie settings link at the foot of the sidebar, above the version footer", () => {
    render(<AdminLayout active="dashboard">Content</AdminLayout>);
    const link = screen.getByRole("button", { name: "Cookie settings" });
    expect(screen.getByRole("navigation", { name: "Admin navigation" }).contains(link)).toBe(true);
    const version = screen.getByRole("contentinfo");
    expect(version.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  });

  it("re-opens the consent banner from the Cookie settings link", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      "questtour-consent",
      JSON.stringify({ choice: "declined", at: "2026-10-09T10:00:00.000Z" }),
    );
    render(
      <>
        <ConsentBanner />
        <AdminLayout active="dashboard">Content</AdminLayout>
      </>,
    );
    expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cookie settings" }));
    expect(screen.getByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
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
