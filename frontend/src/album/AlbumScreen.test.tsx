import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { AlbumScreen } from "./AlbumScreen";
import type { Album } from "./types";

const album: Album = {
  game: "Sofia Old Town Quest", team: "The Explorers", time_zone: "Europe/Sofia",
  played_on: "2026-10-03T07:30:00Z", ended_at: "2026-10-03T10:28:30Z", end_reason: "finished",
  task_count: 6, total_seconds: 10710, rank: 2, shared_rank: false,
  host_message: "Thank you for exploring Sofia with us!\n\nHere is your journey.",
  chapters: [
    { number: 1, landmark: "Lily Pond", landmark_i18n: { de: "Seerosenteich" },
      story: "Laid out by Daniel Neff.\n\nKnown as the Fish Pond.", story_i18n: { de: "Von Daniel Neff angelegt." },
      reached_at: "2026-10-03T07:58:00Z", seconds: 28 * 60, hints: 0, penalty_minutes: 0,
      photos: [{ id: 1, url: "https://example.test/lily-1.jpg", taken_at: "2026-10-03T08:02:00Z" }] },
    { number: 2, landmark: "Eagles' Bridge", landmark_i18n: {}, story: "Built in 1891.", story_i18n: {},
      reached_at: "2026-10-03T08:22:00Z", seconds: 19 * 60, hints: 1, penalty_minutes: 10,
      photos: [
        { id: 2, url: "https://example.test/bridge-1.jpg", taken_at: "2026-10-03T08:26:00Z" },
        { id: 3, url: "https://example.test/bridge-2.jpg", taken_at: "2026-10-03T08:29:00Z" },
        { id: 4, url: "https://example.test/bridge-3.jpg", taken_at: "2026-10-03T08:32:00Z" },
      ] },
  ],
};

it("opens with the game, the team and the facts of the day", () => {
  render(<AlbumScreen album={album} />);
  const cover = screen.getByRole("region", { name: "Cover" });
  expect(within(cover).getByRole("heading", { level: 1, name: "Sofia Old Town Quest" })).toBeInTheDocument();
  expect(within(cover).getByText("The Explorers")).toBeInTheDocument();
  const facts = within(cover).getByRole("list", { name: "The day in numbers" });
  expect(facts).toHaveTextContent("Saturday, 3 October 2026");
  expect(facts).toHaveTextContent("2 of 6 landmarks");
  expect(facts).toHaveTextContent("02:58:30");
  expect(facts).toHaveTextContent("2nd place");
  expect(screen.getByText("Thank you for exploring Sofia with us!")).toBeInTheDocument();
});

it("tells one chapter per landmark: time reached, photos with captions and what the place is, no riddle", () => {
  render(<AlbumScreen album={album} />);
  const chapter = screen.getByRole("region", { name: "Eagles' Bridge" });
  expect(chapter).toHaveTextContent("Landmark 2 of 6 · 11:22");
  const photos = within(chapter).getAllByRole("img");
  expect(photos).toHaveLength(3);
  expect(photos[0]).toHaveAttribute("alt", "The Explorers at Eagles' Bridge, 11:26");
  expect(within(chapter).getAllByText(/Team photo · /)).toHaveLength(3);
  expect(within(chapter).getByText("About this place")).toBeInTheDocument();
  expect(within(chapter).getByText("Built in 1891.")).toBeInTheDocument();
  expect(within(chapter).queryByText(/riddle/i)).not.toBeInTheDocument();   // the end sheet counts riddle minutes
  expect(screen.getByRole("region", { name: "Lily Pond" })).toHaveTextContent("Known as the Fish Pond.");
});

it("leaves out the time and the place for a run that ended unfinished", () => {
  render(<AlbumScreen album={{ ...album, total_seconds: null, rank: null }} />);
  for (const facts of screen.getAllByRole("list", { name: "The day in numbers" })) {
    expect(facts).toHaveTextContent("2 of 6 landmarks");
    expect(facts).not.toHaveTextContent("02:58:30");
    expect(facts).not.toHaveTextContent("place");
  }
});

it("ends with a summary that stands alone: the facts again and the route with minutes and times", () => {
  render(<AlbumScreen album={album} />);
  const end = screen.getByRole("region", { name: "The end" });
  expect(within(end).getByRole("list", { name: "The day in numbers" })).toHaveTextContent("Saturday, 3 October 2026");
  expect(within(end).getByRole("list", { name: "The day in numbers" })).toHaveTextContent("2nd place");
  const route = within(end).getByRole("list", { name: "The route" });
  const stops = within(route).getAllByRole("listitem");
  expect(stops).toHaveLength(2);
  expect(stops[0]).toHaveTextContent("1Lily Pond28 min10:58");
  expect(stops[1]).toHaveTextContent("2Eagles' Bridge19 min11:22");
  expect(within(stops[0]).queryByRole("img")).not.toBeInTheDocument();
  expect(within(stops[1]).getByRole("img", { name: "1 hint" })).toBeInTheDocument();   // a gold dot
  // 47 min of riddles + 10 min for the hint + the breaks past their 5-minute grace = the 02:58:30 in the facts
  const totals = within(end).getByLabelText("Time in total");
  expect(totals).toHaveTextContent("Riddles 47 min");
  expect(totals).toHaveTextContent("Hints and reveals +10 min");
  expect(totals).toHaveTextContent("Long breaks +2 h 1 min");
  expect(totals).toHaveTextContent("On the clock 2 h 58 min");
});

it("leaves out the totals line for a run whose riddles were never timed", () => {
  const untimed = { ...album, total_seconds: null, chapters: album.chapters.map((c) => ({ ...c, seconds: null })) };
  render(<AlbumScreen album={untimed} />);
  const end = screen.getByRole("region", { name: "The end" });
  expect(within(end).queryByLabelText("Time in total")).not.toBeInTheDocument();
  expect(within(within(end).getByRole("list", { name: "The route" })).getAllByRole("listitem")[0]).toHaveTextContent("1Lily Pond10:58");
});

it("closes with a contact sheet of every photo and numbered running feet", () => {
  const { container } = render(<AlbumScreen album={album} />);
  const contact = screen.getByLabelText("All the team's photos");
  expect(within(contact).getAllByRole("img")).toHaveLength(4);
  const feet = container.querySelectorAll(".qa-foot");
  expect(feet).toHaveLength(3);                               // two chapters and the end; the cover has none
  expect(feet[0]).toHaveTextContent("2 / 4");
  expect(feet[2]).toHaveTextContent("4 / 4");
});

it("downloads the stored PDF when the album has one", () => {
  render(<AlbumScreen album={album} pdfUrl="/api/play/t/album.pdf" />);
  const links = screen.getAllByRole("link", { name: "Download PDF" });
  expect(links).toHaveLength(2);
  expect(links[0]).toHaveAttribute("href", "/api/play/t/album.pdf");
  expect(links[0]).toHaveAttribute("download");
  expect(screen.queryByRole("button", { name: "Save as PDF" })).not.toBeInTheDocument();
});

it("falls back to Save as PDF (the print dialog) without a stored PDF, as in the preview", async () => {
  const print = vi.spyOn(window, "print").mockImplementation(() => {});
  render(<AlbumScreen album={album} />);
  const buttons = screen.getAllByRole("button", { name: "Save as PDF" });
  expect(buttons).toHaveLength(2);
  await userEvent.click(buttons[0]);
  expect(print).toHaveBeenCalledTimes(1);
  print.mockRestore();
});

it("offers the game's languages and shows landmark and story in the chosen one", () => {
  render(<AlbumScreen album={album} language="de" />);
  expect(screen.getByRole("button", { name: "Language, DE" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Seerosenteich" })).toHaveTextContent("Von Daniel Neff angelegt.");
  expect(screen.getByRole("region", { name: "Eagles' Bridge" })).toHaveTextContent("Built in 1891.");   // no German: base text
});

it("shows no language pill when nothing is translated", () => {
  const plain = { ...album, chapters: album.chapters.map((c) => ({ ...c, landmark_i18n: {}, story_i18n: {} })) };
  render(<AlbumScreen album={plain} />);
  expect(screen.queryByRole("button", { name: /^Language/ })).not.toBeInTheDocument();
});
