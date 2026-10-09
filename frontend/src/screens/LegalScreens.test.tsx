import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
