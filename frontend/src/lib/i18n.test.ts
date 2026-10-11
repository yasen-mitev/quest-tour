import { pickText } from "./i18n";

test("pickText falls back to base", () => {
  expect(pickText("base", null, "de")).toBe("base");
  expect(pickText("base", { sr: "Srpski" }, "de")).toBe("base");
});

test("pickText returns translation", () => {
  expect(pickText("base", { de: "Basis" }, "de")).toBe("Basis");
});

test("pickText returns Bulgarian translation", () => {
  expect(pickText("base", { bg: "Основа" }, "bg")).toBe("Основа");
});

test("pickText falls back for blank translation", () => {
  expect(pickText("base", { de: "" }, "de")).toBe("base");
});
