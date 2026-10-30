const pad = (n: number) => String(n).padStart(2, "0");

export function formatHms(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

export function formatLeft(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const rest = `${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
  return `${h > 0 ? `${h}:` : ""}${rest} left`;
}

export const formatPenalty = (minutes: number) => `+${minutes} min`;

/** Whole minutes in words, for the album's totals line: "2 h 21 min", "1 h", "45 min". */
export function formatHm(totalSeconds: number): string {
  const total = Math.floor(Math.max(0, totalSeconds) / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h > 0 && m > 0) return `${h} h ${m} min`;
  return h > 0 ? `${h} h` : `${m} min`;
}

export function formatHours(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const hours = h > 0 ? `${h} hour${h === 1 ? "" : "s"}` : "";
  const mins = m > 0 ? `${m} minute${m === 1 ? "" : "s"}` : "";
  return [hours, mins].filter(Boolean).join(" ");
}

export const formatLimit = (minutes: number) =>
  minutes % 60 === 0 ? `${minutes / 60}-hour` : `${minutes}-minute`;

export function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

function parts(iso: string, timeZone: string, options: Intl.DateTimeFormatOptions) {
  const out: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat("en-GB", { timeZone, ...options }).formatToParts(new Date(iso))) {
    out[p.type] = p.value;
  }
  return out;
}

export function formatDateLong(iso: string, timeZone: string): string {
  const p = parts(iso, timeZone, { day: "numeric", month: "long", year: "numeric" });
  return `${p.day} ${p.month} ${p.year}`;
}

export function formatDateWeekday(iso: string, timeZone: string): string {
  const p = parts(iso, timeZone, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
  return `${p.weekday}, ${p.day} ${p.month} ${p.year}`;
}

/** "Saturday, 3 October 2026": the full weekday, for a keepsake such as the team album. */
export function formatDateFull(iso: string, timeZone: string): string {
  const p = parts(iso, timeZone, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return `${p.weekday}, ${p.day} ${p.month} ${p.year}`;
}

export function formatTime(iso: string, timeZone: string): string {
  const p = parts(iso, timeZone, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return `${p.hour}:${p.minute}`;
}

export const paragraphs = (text: string) =>
  text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
