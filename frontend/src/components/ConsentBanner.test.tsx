import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ConsentBanner } from "./ConsentBanner";

describe("ConsentBanner", () => {
  beforeEach(() => localStorage.clear());

  it("is shown while no consent record exists", () => {
    render(<ConsentBanner app="player" />);
    expect(screen.getByRole("dialog", { name: "About cookies" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy policy" })).toHaveAttribute("href", "/privacy");
  });

  it("names what the player app stores: team link and language choice", () => {
    render(<ConsentBanner app="player" />);
    const banner = screen.getByRole("dialog", { name: "About cookies" });
    expect(banner).toHaveTextContent(/team link/i);
    expect(banner).toHaveTextContent(/language/i);
    expect(banner).not.toHaveTextContent(/sign-in session/i);
  });

  it("names what the admin panel stores: the admin sign-in session", () => {
    render(<ConsentBanner app="admin" />);
    const banner = screen.getByRole("dialog", { name: "About cookies" });
    expect(banner).toHaveTextContent(/sign-in session/i);
    expect(banner).not.toHaveTextContent(/team link/i);
  });

  it("writes an accepted record and dismisses on Accept", async () => {
    const user = userEvent.setup();
    render(<ConsentBanner app="player" />);
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(screen.queryByRole("dialog", { name: "About cookies" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("questtour-consent") ?? "")).toEqual({
      choice: "accepted",
      at: expect.any(String),
    });
  });

  it("writes a declined record and dismisses on Decline", async () => {
    const user = userEvent.setup();
    render(<ConsentBanner app="player" />);
    await user.click(screen.getByRole("button", { name: "Decline" }));
    expect(screen.queryByRole("dialog", { name: "About cookies" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("questtour-consent") ?? "").choice).toBe("declined");
  });

  it("stays dismissed when a record already exists (no reappear on reload)", () => {
    localStorage.setItem(
      "questtour-consent",
      JSON.stringify({ choice: "accepted", at: "2026-10-09T10:00:00.000Z" }),
    );
    render(<ConsentBanner app="player" />);
    expect(screen.queryByRole("dialog", { name: "About cookies" })).not.toBeInTheDocument();
  });
});
