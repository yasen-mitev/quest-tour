import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { LanguageToggle } from "./LanguageToggle";

test("shows a pill with the selected language and no sheet until it is tapped", () => {
  render(<LanguageToggle languages={["de", "sr"]} selected="en" onSelect={() => {}} />);
  const pill = screen.getByRole("button", { name: "Language, EN" });
  expect(pill).toHaveTextContent("EN");
  expect(pill).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("renders nothing for a game without translations", () => {
  const { container } = render(<LanguageToggle languages={[]} selected="en" onSelect={() => {}} />);
  expect(container).toBeEmptyDOMElement();
});

test("opens a sheet listing every language by its own name and selects on tap", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  render(<LanguageToggle languages={["de", "sr", "bg"]} selected="en" onSelect={onSelect} />);
  await user.click(screen.getByRole("button", { name: "Language, EN" }));
  expect(screen.getByRole("dialog", { name: "Language" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Deutsch" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Srpski" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Български" })).toBeInTheDocument();
  await user.click(screen.getByRole("option", { name: "Srpski" }));
  expect(onSelect).toHaveBeenCalledWith("sr");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Language, EN" })).toHaveFocus();
});

test("marks the current language as selected and focuses it when the sheet opens", async () => {
  const user = userEvent.setup();
  render(<LanguageToggle languages={["de"]} selected="de" onSelect={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Language, DE" }));
  const current = screen.getByRole("option", { name: "Deutsch" });
  expect(current).toHaveAttribute("aria-selected", "true");
  expect(current).toHaveFocus();
  expect(screen.getByRole("option", { name: "English" })).toHaveAttribute("aria-selected", "false");
});

test("closes on Escape or a tap outside without changing the selection", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  render(<LanguageToggle languages={["de"]} selected="en" onSelect={onSelect} />);
  await user.click(screen.getByRole("button", { name: "Language, EN" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Language, EN" }));
  await user.click(screen.getByRole("dialog").parentElement!);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(onSelect).not.toHaveBeenCalled();
});
