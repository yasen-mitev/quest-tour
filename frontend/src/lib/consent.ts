import { useCallback, useSyncExternalStore } from "react";

// The consent record is the single source of truth for "has this browser been asked, and what
// did it answer?". Everything stored today is strictly necessary (team link, language choice,
// admin session cookie), so nothing is gated on the answer yet — but any future non-essential
// storage or analytics must check `useConsent().consent` before it loads or writes. Storing the
// record itself is exempt: it is what makes the consent demonstrable.

export type ConsentChoice = "accepted" | "declined";

export interface ConsentRecord {
  choice: ConsentChoice;
  at: string;                                    // ISO timestamp of the answer
}

const STORAGE_KEY = "questtour-consent";

function isRecord(value: unknown): value is ConsentRecord {
  return typeof value === "object" && value !== null
    && ((value as ConsentRecord).choice === "accepted" || (value as ConsentRecord).choice === "declined")
    && typeof (value as ConsentRecord).at === "string"
    && !Number.isNaN(Date.parse((value as ConsentRecord).at));
}

function parseRecord(raw: string | null): ConsentRecord | null {
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (isRecord(parsed)) return parsed;
  } catch { /* corrupt record */ }
  return null;                                   // anything unreadable counts as "not asked yet"
}

// Memoized by the raw stored string, so repeated reads return the same object
// (useSyncExternalStore requires a stable snapshot).
let lastRaw: string | null | undefined;
let lastValue: ConsentRecord | null = null;

// When localStorage is unwritable (blocked storage, private modes), the answer is kept here for
// the current session instead — the banner must dismiss and the decision must not be lost.
let memoryRecord: ConsentRecord | null = null;

function readConsent(): ConsentRecord | null {
  if (memoryRecord !== null) return memoryRecord;
  let raw: string | null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;                                 // storage blocked: treat as not asked yet
  }
  if (raw !== lastRaw) {
    lastRaw = raw;
    lastValue = parseRecord(raw);
  }
  return lastValue;
}

function writeConsent(choice: ConsentChoice): void {
  const record: ConsentRecord = { choice, at: new Date().toISOString() };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    memoryRecord = record;                       // storage unwritable: keep the answer for this session
  }
  emit();
}

function reopenConsent(): void {
  memoryRecord = null;
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore private-mode errors */ }
  emit();
}

// One module-level store, so the banner and every "Cookie settings" link agree no matter
// which component each lives in.
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useConsent(): {
  consent: ConsentRecord | null;
  accept(): void;
  decline(): void;
  reopen(): void;
} {
  const consent = useSyncExternalStore(subscribe, readConsent);
  const accept = useCallback(() => writeConsent("accepted"), []);
  const decline = useCallback(() => writeConsent("declined"), []);
  const reopen = useCallback(reopenConsent, []);
  return { consent, accept, decline, reopen };
}
