import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  beforeEach(() => localStorage.clear());

  it("shows the 404 page for an unknown path", () => {
    render(<App path="/no/such/page" />);
    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(screen.getByText("Error 404")).toBeInTheDocument();
  });

  it("asks for the game link at / when no token is remembered", () => {
    render(<App path="/" />);
    expect(screen.getByText("Open your game link")).toBeInTheDocument();
    expect(screen.queryByText("Error 404")).not.toBeInTheDocument();
  });

  it("serves the team album preview at /album/preview and copying is allowed there", () => {
    render(<App path="/album/preview" />);
    expect(screen.getByText("Team album")).toBeInTheDocument();
    const event = new Event("copy", { bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("shows the 404 page for a mangled %-escape in the token", () => {
    render(<App path="/play/%E0%A4%A" />);
    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });

  it("blocks copy/cut/context-menu/select events so riddle text can't be googled", () => {
    render(<App path="/" />);
    const prevent = (type: string) => {
      const event = new Event(type, { bubbles: true, cancelable: true });
      document.body.dispatchEvent(event);
      return event.defaultPrevented;
    };
    for (const type of ["copy", "cut", "contextmenu", "selectstart"]) {
      expect(prevent(type), type).toBe(true);
    }
  });

  it.each(["/", "/admin", "/play/some-token", "/album/preview", "/no/such/page"])(
    "shows the cookie consent banner on %s until an answer is stored",
    (path) => {
      render(<App path={path} />);
      expect(screen.getByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
    },
  );

  it("dismisses the cookie consent banner once an answer is stored", async () => {
    const user = userEvent.setup();
    render(<App path="/" />);
    expect(screen.getByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Decline" }));
    expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
  });

  it("still allows copy/selection inside the answer input", () => {
    render(
      <div className="qc-input">
        <input defaultValue="answer" />
      </div>,
    );
    const event = new Event("copy", { bubbles: true, cancelable: true });
    screen.getByRole("textbox").dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});
