import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { GameHeader } from "./GameHeader";

const base = { elapsed_seconds: 4365, running: true, grace_seconds_remaining: null, penalty_minutes: 25, remaining_seconds: 10035, warning: false };
const common = { availableLanguages: ["de", "sr"], language: "en", onLanguageChange: () => {} };

it("shows clock, penalty and progress", () => {
  render(<GameHeader clock={base} position={2} taskCount={8} receivedAt={Date.now()} onTimeUp={() => {}} {...common} />);
  expect(screen.getByText("01:12:45")).toBeInTheDocument();
  expect(screen.getByText("+25 min")).toBeInTheDocument();
  expect(screen.getByText("Task 3 of 8")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
});

it("hides the penalty tag at zero and switches to warning in the last 15 minutes", () => {
  render(<GameHeader clock={{ ...base, penalty_minutes: 0, elapsed_seconds: 13640, remaining_seconds: 760 }}
                     position={6} taskCount={8} receivedAt={Date.now()} onTimeUp={() => {}} {...common} />);
  expect(screen.queryByText(/\+\d+ min/)).toBeNull();
  expect(screen.getByText("12:40 left")).toBeInTheDocument();
  expect(screen.getByRole("banner")).toHaveClass("qc-header--warning");
});

it("asks the server once when the local countdown reaches zero", () => {
  const onTimeUp = vi.fn();
  const clock = { ...base, remaining_seconds: 0 };
  const { rerender } = render(<GameHeader clock={clock} position={1} taskCount={8} receivedAt={5} onTimeUp={onTimeUp} {...common} />);
  rerender(<GameHeader clock={clock} position={1} taskCount={8} receivedAt={5} onTimeUp={onTimeUp} {...common} />);
  expect(onTimeUp).toHaveBeenCalledTimes(1);
});

it("freezes both clocks while the server says the run is paused", () => {
  vi.useFakeTimers();
  try {
    vi.setSystemTime(new Date("2026-10-14T08:00:00Z"));
    const clock = { ...base, running: false, elapsed_seconds: 300, remaining_seconds: 900 };
    const receivedAt = Date.now();
    const props = { clock, position: 1, taskCount: 8, receivedAt, onTimeUp: () => {}, ...common };
    const { rerender } = render(<GameHeader {...props} />);
    expect(screen.getByText("00:05:00")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(10_000); });
    rerender(<GameHeader {...props} />);
    expect(screen.getByText("00:05:00")).toBeInTheDocument();   // no drift while paused
    expect(screen.getByRole("banner")).not.toHaveClass("qc-header--warning");
  } finally {
    vi.useRealTimers();
  }
});

it("shows the grace countdown while the run is paused within the grace", () => {
  vi.useFakeTimers();
  try {
    vi.setSystemTime(new Date("2026-10-14T08:00:00Z"));
    const clock = { ...base, running: false, grace_seconds_remaining: 240, elapsed_seconds: 300, remaining_seconds: 900 };
    const receivedAt = Date.now();
    const props = { clock, position: 1, taskCount: 8, receivedAt, onTimeUp: () => {}, ...common };
    const { rerender } = render(<GameHeader {...props} />);
    expect(screen.getByText("04:00 left")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(10_000); });
    rerender(<GameHeader {...props} />);
    expect(screen.getByText("03:50 left")).toBeInTheDocument();   // the countdown ticks while paused
    expect(screen.getByRole("banner")).not.toHaveClass("qc-header--warning");
  } finally {
    vi.useRealTimers();
  }
});

it("asks the server once when the local grace countdown reaches zero", () => {
  vi.useFakeTimers();
  try {
    vi.setSystemTime(new Date("2026-10-14T08:00:00Z"));
    const onTimeUp = vi.fn();
    const clock = { ...base, running: false, grace_seconds_remaining: 5, elapsed_seconds: 300, remaining_seconds: 900 };
    const receivedAt = Date.now();
    const props = { clock, position: 1, taskCount: 8, receivedAt, onTimeUp, ...common };
    const { rerender } = render(<GameHeader {...props} />);
    act(() => { vi.advanceTimersByTime(6_000); });
    rerender(<GameHeader {...props} />);
    expect(onTimeUp).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

it("renders the language menu with available languages", async () => {
  const user = userEvent.setup();
  render(<GameHeader clock={base} position={0} taskCount={8} receivedAt={Date.now()} onTimeUp={() => {}} {...common} />);
  expect(screen.getByRole("button", { name: "Language, EN" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Language, EN" }));
  expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Deutsch" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Srpski" })).toBeInTheDocument();
});
