import type { RiddleRatingRow } from "../api/types";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { RiddleRatings } from "./RiddleRatings";

const rows: RiddleRatingRow[] = [
  { position: 0, landmark_name: "Alexander Nevsky Cathedral",
    landmark_name_i18n: { bg: "Катедрала Александър Невски" }, rating: 4 },
  { position: 1, landmark_name: "Sofia University",
    landmark_name_i18n: {}, rating: null },
];

it("lists each completed riddle with this phone's stars pre-filled", () => {
  render(<RiddleRatings riddles={rows} language="en" onRate={() => {}} />);
  const first = screen.getByRole("radiogroup", { name: "Rate 1. Alexander Nevsky Cathedral" });
  expect(within(first).getByRole("radio", { name: "4 stars" })).toBeChecked();
  const second = screen.getByRole("radiogroup", { name: "Rate 2. Sofia University" });
  expect(within(second).queryByRole("radio", { checked: true })).toBeNull();
});

it("shows landmark names in the selected language", () => {
  render(<RiddleRatings riddles={rows} language="bg" onRate={() => {}} />);
  expect(screen.getByText("Катедрала Александър Невски")).toBeInTheDocument();
  expect(screen.getByText("Sofia University")).toBeInTheDocument();
});

it("reports the riddle position and stars on tap, and renders nothing without riddles", () => {
  const onRate = vi.fn();
  const { container, rerender } = render(<RiddleRatings riddles={rows} language="en" onRate={onRate} />);
  fireEvent.click(within(screen.getByRole("radiogroup", { name: "Rate 2. Sofia University" })).getByRole("radio", { name: "5 stars" }));
  expect(onRate).toHaveBeenCalledWith(1, 5);
  rerender(<RiddleRatings riddles={[]} language="en" onRate={onRate} />);
  expect(container).toBeEmptyDOMElement();
});

it("renders nothing when an old backend leaves riddles out (deploy skew)", () => {
  const { container } = render(
    <RiddleRatings riddles={undefined as unknown as RiddleRatingRow[]} language="en" onRate={() => {}} />,
  );
  expect(container).toBeEmptyDOMElement();
});
