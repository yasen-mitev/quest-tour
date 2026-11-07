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

function RulesHarness() {
  const [value, setValue] = useState("");
  const [repeat, setRepeat] = useState("");
  return (
    <>
      <PasswordField label="New password" value={value} onChange={setValue} autoComplete="new-password" minLength={12} />
      <PasswordField label="Repeat new password" value={repeat} onChange={setRepeat} autoComplete="new-password"
                     matches={value} />
    </>
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

  describe("live rules", () => {
    it("shows the length rule up front and counts down while typing", async () => {
      const user = setup();
      render(<RulesHarness />);
      const input = screen.getByLabelText("New password");
      expect(input).toHaveAccessibleDescription("At least 12 characters");
      await user.type(input, "12345678");
      expect(input).toHaveAccessibleDescription("At least 12 characters (4 more)");
      expect(screen.getByText("At least 12 characters (4 more)").closest(".admin-rule")).not.toHaveClass("admin-rule--met");
    });

    it("marks the length rule as met at 12 characters", async () => {
      const user = setup();
      render(<RulesHarness />);
      const input = screen.getByLabelText("New password");
      await user.type(input, "123456789012");
      expect(input).toHaveAccessibleDescription("At least 12 characters");
      expect(screen.getByText("At least 12 characters").closest(".admin-rule")).toHaveClass("admin-rule--met");
    });

    it("announces only when the rule flips, not on every keystroke", async () => {
      const user = setup();
      render(<RulesHarness />);
      const input = screen.getByLabelText("New password");
      const live = () => screen.getAllByRole("status").map((el) => el.textContent).join("|");
      await user.type(input, "12345678901");
      expect(live()).toBe("|");
      await user.type(input, "2");
      expect(live()).toBe("At least 12 characters: done|");
    });

    it("says nothing about matching until the repeat field is typed in", async () => {
      const user = setup();
      render(<RulesHarness />);
      const repeat = screen.getByLabelText("Repeat new password");
      expect(screen.queryByText(/match/i)).not.toBeInTheDocument();
      await user.type(screen.getByLabelText("New password"), "a-long-enough-password");
      await user.type(repeat, "a-long");
      expect(repeat).toHaveAccessibleDescription("Doesn't match yet");
      await user.type(repeat, "-enough-password");
      expect(repeat).toHaveAccessibleDescription("Passwords match");
      expect(screen.getByText("Passwords match").closest(".admin-rule")).toHaveClass("admin-rule--met");
    });
  });
});
