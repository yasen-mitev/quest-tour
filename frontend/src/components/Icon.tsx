import type { ReactElement } from "react";

// Filled glyphs (direction 02c "Evening Domes · Cards"): solid shapes with even-odd cut-outs, so they read at
// 16–20 px on any ground. Arrows, loops and lines stay strokes, as in every filled icon set.
const FILLED = {
  clock: <><path fillRule="evenodd" d="M12 4a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm-1 4h2v4.6l3 1.7-1 1.7-4-2.3z" /><rect x="9" y="1.5" width="6" height="2" rx="1" /></>,
  riddle: <><path fillRule="evenodd" d="M8 10.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zm0 3a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z" /><path d="M10.6 12.9l-1.5-1.5L19.2 1.3l1.5 1.5-1.4 1.4 1.4 1.4-1.5 1.5-1.4-1.4-1.1 1.1 1.4 1.4-1.5 1.5-1.4-1.4z" /></>,
  camera: <><path fillRule="evenodd" d="M9 4l-2 3H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-3l-2-3zm3 5.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" /><circle cx="12" cy="13.5" r="2.2" /></>,
  lock: <><rect x="4" y="10" width="16" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" strokeWidth={2.4} /></>,
  flag: <><rect x="4" y="3" width="2.4" height="18" rx="1.2" /><path d="M6.4 4h11.6l-2.2 4 2.2 4H6.4z" /></>,
  error: <path fillRule="evenodd" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM8.7 7.3L12 10.6l3.3-3.3 1.4 1.4L13.4 12l3.3 3.3-1.4 1.4L12 13.4l-3.3 3.3-1.4-1.4L10.6 12 7.3 8.7z" />,
  shield: <path fillRule="evenodd" d="M12 2l8 3v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V5zm-1.4 13.4L6.6 11.4 8 10l2.6 2.6 5.4-5.4L17.4 8.6z" />,
  team: <><circle cx="9" cy="8" r="3.5" /><circle cx="17" cy="10" r="2.5" /><path d="M3 20a6 6 0 0 1 12 0z" /><path d="M14.5 20a4.5 4.5 0 0 1 7 0z" /></>,
  trophy: <path fillRule="evenodd" d="M7 3h10v2h3v2a4 4 0 0 1-4 4h-.3A6 6 0 0 1 13 14.9V18h3v3H8v-3h3v-3.1A6 6 0 0 1 8.3 11H8a4 4 0 0 1-4-4V5h3zM4.9 7a2.1 2.1 0 0 0 2.1 2.1V7zM17 9.1A2.1 2.1 0 0 0 19.1 7H17z" />,
  gift: <><path d="M3 8h18v4H3z" /><path d="M4 13h7v8H4zM13 13h7v8h-7z" /><path d="M12 8c-1-3-5-4-5-1.5S10.5 8 12 8zm0 0c1-3 5-4 5-1.5S13.5 8 12 8z" fill="none" stroke="currentColor" strokeWidth={2} /></>,
  gallery: <path fillRule="evenodd" d="M3 4a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1zm6 4a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM4 18l5-5 3 3 4-4 4 4v2z" />,
  list: <><rect x="7" y="5" width="14" height="2.4" rx="1.2" /><rect x="7" y="10.8" width="14" height="2.4" rx="1.2" /><rect x="7" y="16.6" width="10" height="2.4" rx="1.2" /><circle cx="4" cy="6.2" r="1.4" /><circle cx="4" cy="12" r="1.4" /><circle cx="4" cy="17.8" r="1.4" /></>,
  bulb: <><path d="M12 2a7 7 0 0 0-4.6 12.3c.8.7 1.6 1.7 1.6 2.7h6c0-1 .8-2 1.6-2.7A7 7 0 0 0 12 2z" /><rect x="9" y="18.5" width="6" height="2" rx="1" /><rect x="10" y="21" width="4" height="1.8" rx=".9" /></>,
  calendar: <><path fillRule="evenodd" d="M4 5h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm1 6v8h14v-8z" /><rect x="7" y="2" width="2.4" height="5" rx="1.2" /><rect x="14.6" y="2" width="2.4" height="5" rx="1.2" /></>,
  compass: <path fillRule="evenodd" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.5 5.5l-2.6 6.4-6.4 2.6 2.6-6.4z" />,
  star: <path d="M12 2.8l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.7l-5.9 3.1 1.2-6.5L2.5 9.7l6.6-.9z" />,
} satisfies Record<string, ReactElement>;

// Stroke glyphs: lines and arrows have no fill to speak of
const STROKED = {
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c-2.6 2.5-3.9 5.5-3.9 9s1.3 6.5 3.9 9c2.6-2.5 3.9-5.5 3.9-9S14.6 5.5 12 3z" /></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  download: <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />,
  retry: <path d="M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15M4 20v-5h5" />,
  wifiOff: <><path d="M2 8.8a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0" /><circle cx="12" cy="19.5" r="1.2" fill="currentColor" stroke="none" /><path d="M3 3l18 18" /></>,
  brokenLink: <path d="M9 15l6-6M10.5 6.5l1-1a4.5 4.5 0 0 1 6.4 6.4l-1 1M13.5 17.5l-1 1a4.5 4.5 0 0 1-6.4-6.4l1-1M3 3l18 18" />,
} satisfies Record<string, ReactElement>;

export type IconName = keyof typeof FILLED | keyof typeof STROKED;     // a literal union, so icon-name typos fail `tsc`

export function Icon({ name, size, className }: { name: IconName; size?: number; className?: string }) {
  const stroked = name in STROKED;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" className={className}
         fill={stroked ? "none" : "currentColor"} stroke={stroked ? "currentColor" : "none"}
         strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      {stroked ? STROKED[name as keyof typeof STROKED] : FILLED[name as keyof typeof FILLED]}
    </svg>
  );
}
