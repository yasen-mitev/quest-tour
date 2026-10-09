import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ContactScreen, LegalLinks, PrivacyScreen, TermsScreen } from "./LegalScreens";

describe("LegalLinks", () => {
  it("links the three pages", () => {
    render(<LegalLinks />);
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("link", { name: "Contact" })).toHaveAttribute("href", "/contact");
  });
});

describe("PrivacyScreen", () => {
  it("describes what is stored and links the contact page", () => {
    render(<PrivacyScreen />);
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText(/team link, your language choice and your cookie-consent answer/i)).toBeInTheDocument();
    expect(screen.getByText(/photos your team takes/i)).toBeInTheDocument();
    expect(screen.getByText(/no analytics, no tracking/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "contact page" })).toHaveAttribute("href", "/contact");
  });
});

describe("TermsScreen", () => {
  it("covers the game, the photos, the team links and the results", () => {
    render(<TermsScreen />);
    expect(screen.getByRole("heading", { name: "Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText(/provided as is/i)).toBeInTheDocument();
    expect(screen.getByText(/collected and kept by your host/i)).toBeInTheDocument();
    expect(screen.getByText(/belongs to one team/i)).toBeInTheDocument();
    expect(screen.getByText(/as measured by the app/i)).toBeInTheDocument();
  });
});

describe("ContactScreen", () => {
  it("sends bugs and feature requests to the GitHub project", () => {
    render(<ContactScreen />);
    expect(screen.getByRole("heading", { name: "Contact" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Report a bug" }))
      .toHaveAttribute("href", "https://github.com/yasen-mitev/quest-tour/issues/new?title=%5BBug%5D%20");
    expect(screen.getByRole("link", { name: "Request a feature" }))
      .toHaveAttribute("href", "https://github.com/yasen-mitev/quest-tour/issues/new?title=%5BFeature%5D%20");
  });
});

it("every legal page offers the other pages", () => {
  for (const Screen of [PrivacyScreen, TermsScreen, ContactScreen]) {
    const { unmount } = render(<Screen />);
    expect(screen.getByRole("contentinfo", { name: "Legal and contact" })).toBeInTheDocument();
    unmount();
  }
});

describe("Back", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is offered on every legal page", () => {
    for (const Screen of [PrivacyScreen, TermsScreen, ContactScreen]) {
      const { unmount } = render(<Screen />);
      expect(screen.getByRole("button", { name: "← Back" })).toBeInTheDocument();
      unmount();
    }
  });

  it("returns to the welcome page (via the app root) for guests", async () => {
    vi.stubGlobal("location", { href: "", search: "" });
    render(<PrivacyScreen />);
    await userEvent.click(screen.getByRole("button", { name: "← Back" }));
    expect(window.location.href).toBe("/");
  });

  it("returns to the admin dashboard when the visit came from the admin panel", async () => {
    vi.stubGlobal("location", { href: "", search: "?from=admin" });
    render(<TermsScreen />);
    await userEvent.click(screen.getByRole("button", { name: "← Back" }));
    expect(window.location.href).toBe("/admin");
  });

  it("keeps the origin when the legal pages link each other", () => {
    vi.stubGlobal("location", { href: "", search: "?from=admin" });
    render(<LegalLinks />);
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy?from=admin");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms?from=admin");
    expect(screen.getByRole("link", { name: "Contact" })).toHaveAttribute("href", "/contact?from=admin");
  });

  it("links plainly when there is no origin to keep", () => {
    vi.stubGlobal("location", { href: "", search: "" });
    render(<LegalLinks />);
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
  });
});
