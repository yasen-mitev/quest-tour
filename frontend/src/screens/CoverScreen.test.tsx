import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ConsentBanner } from "../components/ConsentBanner";
import { APP_VERSION, versionLabel } from "../lib/version";
import { makeState } from "../test/fixtures";
import { CoverScreen } from "./CoverScreen";

const frame = { header: null, offline: false, notice: null, onNoticeDone: () => {} };
function notStarted() {
  const state = makeState({ phase: null, status: "not_started", clock: null, task: null });
  return { ...state, game: { ...state.game, available_languages: ["de", "sr"] } };
}

function renderCover(props: { onLanguageChange?: (lang: string) => void; onContinue?: () => void } = {}) {
  return render(
    <CoverScreen state={notStarted()} frame={frame} language="en"
                 onLanguageChange={props.onLanguageChange ?? vi.fn()}
                 onContinue={props.onContinue ?? vi.fn()} />,
  );
}

it("shows the game name, the riddle count and the team", () => {
  renderCover();
  expect(screen.getByRole("heading", { name: "Sofia Old Town Quest" })).toBeInTheDocument();
  expect(screen.getByText("A city quest in 8 riddles")).toBeInTheDocument();
  expect(screen.getByText("Welcome, The Explorers")).toBeInTheDocument();
});

it("shows the running version in the footer (issue #29)", () => {
  renderCover();
  expect(screen.getAllByRole("contentinfo").find((f) => f.textContent?.includes(versionLabel(APP_VERSION))))
    .toBeDefined();
});

it("offers the language menu and continues to the Welcome page", async () => {
  const onLanguageChange = vi.fn();
  const onContinue = vi.fn();
  renderCover({ onLanguageChange, onContinue });
  await userEvent.click(screen.getByRole("button", { name: "Language, EN" }));
  await userEvent.click(screen.getByRole("option", { name: "Deutsch" }));
  expect(onLanguageChange).toHaveBeenCalledWith("de");
  await userEvent.click(screen.getByRole("button", { name: "How it works" }));
  expect(onContinue).toHaveBeenCalledTimes(1);
});

it("offers the legal and contact pages next to the How it works button", () => {
  renderCover();
  expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
  expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
  expect(screen.getByRole("link", { name: "Contact" })).toHaveAttribute("href", "/contact");
});

it("re-opens the cookie dialog from the first page", async () => {
  localStorage.setItem(
    "questtour-consent",
    JSON.stringify({ choice: "accepted", at: "2026-10-09T10:00:00.000Z" }),
  );
  const user = userEvent.setup();
  // The banner is mounted by App next to the screen, not inside it
  render(
    <>
      <ConsentBanner app="player" />
      <CoverScreen state={notStarted()} frame={frame} language="en"
                   onLanguageChange={vi.fn()} onContinue={vi.fn()} />
    </>,
  );
  expect(screen.queryByRole("dialog", { name: "About cookies" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Cookies" }));
  expect(screen.getByRole("dialog", { name: "About cookies" })).toBeInTheDocument();
});
