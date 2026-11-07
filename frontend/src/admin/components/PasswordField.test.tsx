import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PasswordField, REVEAL_MS } from "./PasswordField";

function Harness({ onSubmit = () => {} }: { onSubmit?: () => void }) {
  const [value, setValue] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
      <PasswordField label="Password" value={value} onChange={setValue} autoComplete="current-password" />
    </form>
  );
}

describe("PasswordField", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  const setup = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

  it("is a labelled password input, hidden by default", () => {
    render(<Harness />);
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
  });

  it("shows the typed password and hides it again after a few seconds", async () => {
    const user = setup();
    render(<Harness />);
    const input = screen.getByLabelText("Password");
    await user.type(input, "secret-value");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveValue("secret-value");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(REVEAL_MS - 100));
    expect(input).toHaveAttribute("type", "text");
    act(() => vi.advanceTimersByTime(100));
    expect(input).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
  });

  it("hides right away on a second click", async () => {
    const user = setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Show password" }));
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("does not submit the form", async () => {
    const user = setup();
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
