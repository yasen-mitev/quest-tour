import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { makeState, makeTask, NEVSKY } from "../test/fixtures";
import { CorrectScreen } from "./CorrectScreen";
import { LandmarkScreen } from "./LandmarkScreen";
import { LoadingScreen } from "./LoadingScreen";
import { NotFoundScreen } from "./NotFoundScreen";
import { RevealedScreen } from "./RevealedScreen";

const frame = { header: null, offline: false, notice: null, onNoticeDone: () => {} };

it("LoadingScreen shows the copy and the banner only when offline", () => {
  const { rerender } = render(<LoadingScreen offline={false} />);
  expect(screen.getByText("Loading your quest…")).toBeInTheDocument();
  expect(screen.queryByText("No connection – retrying…")).toBeNull();
  rerender(<LoadingScreen offline />);
  expect(screen.getByText("No connection – retrying…")).toBeInTheDocument();
});

it("CorrectScreen names the landmark and continues to the photo", async () => {
  const onContinue = vi.fn();
  const landmark = { ...NEVSKY, name_i18n: { de: "Alexander-Newski-Kathedrale" } };
  render(<CorrectScreen state={makeState({ task: makeTask({ completion: "answered", landmark }) })} frame={frame} language="de" onRate={vi.fn()} onContinue={onContinue} />);
  expect(screen.getByText("Correct!")).toBeInTheDocument();
  expect(screen.getByText("Alexander-Newski-Kathedrale")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Take a photo, create a memory" }));
  expect(onContinue).toHaveBeenCalledTimes(1);
});

it("RevealedScreen shows the answer and the charged penalty", async () => {
  const onContinue = vi.fn();
  const task = makeTask({
    completion: "revealed",
    revealed_answer: "Alexander Nevsky Cathedral",
    reveal_penalty_minutes: 30,
    text_i18n: { de: "Goldene Kuppeln leuchten über dem Platz, der meinen Namen trägt." },
    landmark: { ...NEVSKY, name_i18n: { de: "Alexander-Newski-Kathedrale" } },
  });
  render(<RevealedScreen state={makeState({ task })} frame={frame} language="de" onRate={vi.fn()} onContinue={onContinue} />);
  expect(screen.getByText("The answer")).toBeInTheDocument();
  expect(screen.getByText("Alexander Nevsky Cathedral")).toBeInTheDocument();
  expect(screen.getByText("+30 min added")).toBeInTheDocument();
  expect(screen.getByText("Head there now – a team photo at Alexander-Newski-Kathedrale unlocks the next riddle.")).toBeInTheDocument();
  expect(screen.getByText("Goldene Kuppeln leuchten über dem Platz, der meinen Namen trägt.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Continue/ }));
  expect(onContinue).toHaveBeenCalledTimes(1);
});

it("LandmarkScreen offers the next riddle and disables itself while busy", async () => {
  let release!: () => void;
  const onNext = vi.fn(() => new Promise<"ok">((resolve) => { release = () => resolve("ok"); }));
  const task = makeTask({ completion: "answered", landmark: { ...NEVSKY, name_i18n: { de: "Alexander-Newski-Kathedrale" } }, photo_count: 1, picture_url: null });
  const { container } = render(<LandmarkScreen state={makeState({ phase: "info", task })} frame={frame} language="de" onNext={onNext} />);
  expect(screen.getByText("Landmark 3 of 8")).toBeInTheDocument();
  expect(screen.getByText("Alexander-Newski-Kathedrale")).toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
  const button = screen.getByRole("button", { name: /Next riddle/ });
  await userEvent.click(button);
  expect(button).toBeDisabled();
  await act(async () => { release(); });
  await vi.waitFor(() => expect(button).toBeEnabled());
});

it("LandmarkScreen on the last task shows the results card and translated tourist info", () => {
  const task = makeTask({
    completion: "answered",
    landmark: {
      ...NEVSKY,
      picture_url: "/api/images/n.svg",
      name_i18n: { de: "Alexander-Newski-Kathedrale" },
      info_i18n: { de: "Erbaut 1882–1912.\n\nEine der größten." },
    },
    photo_count: 1,
  });
  render(<LandmarkScreen state={makeState({ phase: "info", position: 7, task })} frame={frame} language="de" onNext={vi.fn()} />);
  expect(screen.getByText("That was the last landmark!")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /See results/ })).toBeInTheDocument();
  expect(screen.getByAltText("Picture of Alexander-Newski-Kathedrale")).toBeInTheDocument();
  expect(screen.getByText("Alexander-Newski-Kathedrale")).toBeInTheDocument();
  expect(screen.getByText("Erbaut 1882–1912.")).toBeInTheDocument();
  expect(screen.getByText("Eine der größten.")).toBeInTheDocument();
});

it("CorrectScreen falls back to base landmark name when translation is missing", () => {
  render(<CorrectScreen state={makeState({ task: makeTask({ completion: "answered", landmark: NEVSKY }) })} frame={frame} language="de" onRate={vi.fn()} onContinue={vi.fn()} />);
  expect(screen.getByText("Alexander Nevsky Cathedral")).toBeInTheDocument();
});

it("RevealedScreen falls back to base landmark name and recap when translation is missing", () => {
  const task = makeTask({ completion: "revealed", revealed_answer: "x", text_i18n: {}, landmark: NEVSKY });
  render(<RevealedScreen state={makeState({ task })} frame={frame} language="de" onRate={vi.fn()} onContinue={vi.fn()} />);
  expect(screen.getByText("Head there now – a team photo at Alexander Nevsky Cathedral unlocks the next riddle.")).toBeInTheDocument();
  expect(screen.getByText("Golden domes shine over the square that bears my name. I was built to honour soldiers who fell for this land's freedom. Who am I?")).toBeInTheDocument();
});

it("LandmarkScreen image placeholder uses the translated landmark name", () => {
  const task = makeTask({
    completion: "answered",
    landmark: {
      ...NEVSKY,
      picture_url: "/api/images/broken.svg",
      name_i18n: { de: "Alexander-Newski-Kathedrale" },
    },
    photo_count: 1,
  });
  const { container } = render(<LandmarkScreen state={makeState({ phase: "info", task })} frame={frame} language="de" onNext={vi.fn()} />);
  const img = container.querySelector("img");
  expect(img).not.toBeNull();
  fireEvent.error(img!);
  const placeholder = container.querySelector(".qs-pic--placeholder");
  expect(placeholder).toHaveTextContent("Alexander-Newski-Kathedrale");
});

it("LandmarkScreen falls back to base name and tourist info when translation is missing", () => {
  const task = makeTask({ completion: "answered", landmark: NEVSKY, photo_count: 1, picture_url: null });
  render(<LandmarkScreen state={makeState({ phase: "info", task })} frame={frame} language="de" onNext={vi.fn()} />);
  expect(screen.getByText("Alexander Nevsky Cathedral")).toBeInTheDocument();
  expect(screen.getByText("Built 1882–1912.")).toBeInTheDocument();
});

it("NotFoundScreen shows the 404 caption only for the default title", () => {
  const { rerender } = render(<NotFoundScreen />);
  expect(screen.getByText("Page not found")).toBeInTheDocument();
  expect(screen.getByText("Error 404")).toBeInTheDocument();
  rerender(<NotFoundScreen title="Open your game link" />);
  expect(screen.getByText("Open your game link")).toBeInTheDocument();
  expect(screen.queryByText("Error 404")).toBeNull();
});
