import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ConsentBanner } from "./ConsentBanner";

describe("ConsentBanner", () => {
  beforeEach(() => localStorage.clear());

  it("is shown while no consent record exists", () => {
    render(<ConsentBanner />);
    expect(screen.getByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
  });

  it("names what is stored: team link, language choice and the admin sign-in session", () => {
    render(<ConsentBanner />);
    expect(screen.getByRole("region", { name: "Cookie notice" })).toHaveTextContent(/team link/i);
    expect(screen.getByRole("region", { name: "Cookie notice" })).toHaveTextContent(/language/i);
    expect(screen.getByRole("region", { name: "Cookie notice" })).toHaveTextContent(/sign-in session/i);
  });

  it("writes an accepted record and dismisses on Accept", async () => {
    const user = userEvent.setup();
    render(<ConsentBanner />);
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("questtour-consent") ?? "")).toEqual({
      choice: "accepted",
      at: expect.any(String),
    });
  });

  it("writes a declined record and dismisses on Decline", async () => {
    const user = userEvent.setup();
    render(<ConsentBanner />);
    await user.click(screen.getByRole("button", { name: "Decline" }));
    expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("questtour-consent") ?? "").choice).toBe("declined");
  });

  it("stays dismissed when a record already exists (no reappear on reload)", () => {
    localStorage.setItem(
      "questtour-consent",
      JSON.stringify({ choice: "accepted", at: "2026-10-09T10:00:00.000Z" }),
    );
    render(<ConsentBanner />);
    expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
  });
});
