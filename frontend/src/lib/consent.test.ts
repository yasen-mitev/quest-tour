import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useConsent } from "./consent";

describe("useConsent", () => {
  beforeEach(() => localStorage.clear());

  it("treats a missing record as not asked yet", () => {
    const { result } = renderHook(() => useConsent());
    expect(result.current.consent).toBeNull();
  });

  it("treats a corrupt record as not asked yet", () => {
    localStorage.setItem("questtour-consent", "{not json");
    const { result } = renderHook(() => useConsent());
    expect(result.current.consent).toBeNull();
  });

  it("treats a record with an unknown choice as not asked yet", () => {
    localStorage.setItem("questtour-consent", JSON.stringify({ choice: "maybe", at: "2026-10-09T10:00:00.000Z" }));
    const { result } = renderHook(() => useConsent());
    expect(result.current.consent).toBeNull();
  });

  it.each([
    ["a JSON array", "[]"],
    ["a JSON null", "null"],
    ["a bare number", "123"],
    ["a missing timestamp", JSON.stringify({ choice: "accepted" })],
    ["a non-string timestamp", JSON.stringify({ choice: "accepted", at: 42 })],
    ["an unparseable timestamp", JSON.stringify({ choice: "accepted", at: "not-a-date" })],
  ])("treats %s as not asked yet", (_label, stored) => {
    localStorage.setItem("questtour-consent", stored);
    const { result } = renderHook(() => useConsent());
    expect(result.current.consent).toBeNull();
  });

  it("reads back a stored record", () => {
    localStorage.setItem(
      "questtour-consent",
      JSON.stringify({ choice: "declined", at: "2026-10-09T10:00:00.000Z" }),
    );
    const { result } = renderHook(() => useConsent());
    expect(result.current.consent).toEqual({ choice: "declined", at: "2026-10-09T10:00:00.000Z" });
  });

  it("accept() writes the accepted choice with an ISO timestamp", () => {
    const { result } = renderHook(() => useConsent());
    act(() => result.current.accept());
    expect(result.current.consent?.choice).toBe("accepted");
    const stored = JSON.parse(localStorage.getItem("questtour-consent") ?? "");
    expect(stored.choice).toBe("accepted");
    expect(stored.at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("decline() writes the declined choice", () => {
    const { result } = renderHook(() => useConsent());
    act(() => result.current.decline());
    expect(result.current.consent?.choice).toBe("declined");
    expect(JSON.parse(localStorage.getItem("questtour-consent") ?? "").choice).toBe("declined");
  });

  it("keeps every hook instance in sync", () => {
    const first = renderHook(() => useConsent());
    const second = renderHook(() => useConsent());
    act(() => first.result.current.accept());
    expect(second.result.current.consent?.choice).toBe("accepted");
  });

  it("reopen() asks again and clears the stored answer until a new one is given", () => {
    const { result } = renderHook(() => useConsent());
    act(() => result.current.accept());
    act(() => result.current.reopen());
    expect(result.current.consent).toBeNull();
    expect(localStorage.getItem("questtour-consent")).toBeNull();
    act(() => result.current.decline());
    expect(result.current.consent?.choice).toBe("declined");
  });

  describe("when localStorage writes fail", () => {
    beforeEach(() => {
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("storage blocked", "QuotaExceededError");
      });
    });
    afterEach(() => vi.restoreAllMocks());

    it("accept() still records the answer for the session", () => {
      const { result } = renderHook(() => useConsent());
      act(() => result.current.accept());
      expect(result.current.consent?.choice).toBe("accepted");
    });

    it("decline() still records the answer for the session", () => {
      const { result } = renderHook(() => useConsent());
      act(() => result.current.decline());
      expect(result.current.consent?.choice).toBe("declined");
    });

    it("reopen() asks again after a session-only answer", () => {
      const { result } = renderHook(() => useConsent());
      act(() => result.current.accept());
      act(() => result.current.reopen());
      expect(result.current.consent).toBeNull();
      act(() => result.current.decline());
      expect(result.current.consent?.choice).toBe("declined");
    });
  });
});
