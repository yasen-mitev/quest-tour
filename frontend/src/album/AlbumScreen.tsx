import { useId, useMemo } from "react";
import { AppVersion } from "../components/AppVersion";
import { WelcomeSkyline } from "../components/art";
import { Icon } from "../components/Icon";
import { LanguageToggle } from "../components/LanguageToggle";
import { Paragraphs } from "../components/Paragraphs";
import { formatDateFull, formatHm, formatHms, formatTime, ordinal } from "../lib/format";
import { pickText } from "../lib/i18n";
import type { Album, AlbumChapter, AlbumPhoto } from "./types";

/** The team album (design draft): a keepsake the host shares after the game, laid out as an A4 document.
 *  A cover sheet (the facts of the day and the host's message), one sheet per landmark reached (the team
 *  photo and what the place is, in two columns; no riddles) and a closing sheet with the route (minutes per
 *  riddle, time reached), a totals line and every photo. On a
 *  desktop and in the PDF the sheets are true A4 pages; on a phone the same sheets flow as cards, because
 *  A4 type shrunk to a phone's width would not be readable. "Save as PDF" prints the A4 pages. */
export function AlbumScreen({ album, language = "en", onLanguageChange = () => {}, pdfUrl }: {
  album: Album; language?: string; onLanguageChange?(lang: string): void;
  pdfUrl?: string;   // the stored PDF (GET /api/play/{token}/album.pdf); without it, the print dialog
}) {
  const tz = album.time_zone;
  const pages = album.chapters.length + 2;
  const allPhotos = album.chapters.flatMap((chapter) => chapter.photos.map((photo) => ({ photo, chapter })));
  // The landmark stories carry their translations, so the album offers the same language pill as the game
  const languages = useMemo(() => {
    const codes = new Set<string>();
    for (const chapter of album.chapters) for (const code of [...Object.keys(chapter.landmark_i18n), ...Object.keys(chapter.story_i18n)]) codes.add(code);
    codes.delete("en");
    return [...codes].sort();
  }, [album]);
  return (
    <div className="qa">
      <div className="qa-toolbar">
        <span className="qa-toolbar__title">{album.game}</span>
        <div className="qa-toolbar__tools">
          <LanguageToggle languages={languages} selected={language} onSelect={onLanguageChange} />
          <SavePdfButton pdfUrl={pdfUrl} />
        </div>
      </div>
      <article className="qa-doc" aria-label={`${album.team} – ${album.game}`}>
        <section className="qa-sheet qa-sheet--cover" aria-label="Cover">
          <div className="qa-page">
            <WelcomeSkyline />
            <p className="qs-hero__kicker">Team album</p>
            <h1 className="t-display-l qa-title">{album.game}</h1>
            <span className="qs-team"><Icon name="team" />{album.team}</span>
            <Facts album={album} />
            <section className="qs-card qs-host-card qa-host" aria-label="From your host">
              <p className="qs-eyebrow qs-eyebrow--gold"><Icon name="gift" />From your host</p>
              <Paragraphs text={album.host_message} />
            </section>
          </div>
        </section>

        {album.chapters.map((chapter, i) => (
          <ChapterSheet key={chapter.number} chapter={chapter} album={album} language={language} page={i + 2} pages={pages} />
        ))}

        {/* The closing sheet is a summary that stands on its own when only the last page is printed */}
        <section className="qa-sheet qa-sheet--end" aria-label="The end">
          <div className="qa-page">
            <p className="qs-hero__kicker">The end</p>
            <h2 className="t-display-l qa-title">{album.team}</h2>
            <p className="t-body qa-end__date">{album.game}</p>
            <Facts album={album} light />
            <ol className="qa-route" aria-label="The route">
              {album.chapters.map((chapter) => (
                <li key={chapter.number}>
                  <span className="qa-route__no">{chapter.number}</span>
                  <span className="qa-route__name">
                    {pickText(chapter.landmark, chapter.landmark_i18n, language)}
                    {chapter.hints > 0 && (
                      <span className="qa-route__hints" role="img" aria-label={`${chapter.hints} hint${chapter.hints === 1 ? "" : "s"}`}>
                        {Array.from({ length: chapter.hints }, (_, i) => <i key={i} />)}
                      </span>
                    )}
                  </span>
                  {chapter.seconds !== null && <span className="qa-route__min">{Math.floor(chapter.seconds / 60)} min</span>}
                  <span className="qa-route__time">{formatTime(chapter.reached_at, tz)}</span>
                </li>
              ))}
            </ol>
            <RouteTotals album={album} />
            {allPhotos.length > 0 && (
              <div className="qa-contact" aria-label="All the team's photos">
                {allPhotos.map(({ photo, chapter }) => (
                  <img key={photo.url} src={photo.url}
                       alt={`${album.team} at ${chapter.landmark}, ${formatTime(photo.taken_at, tz)}`} />
                ))}
              </div>
            )}
            <div className="qa-end__save"><SavePdfButton pdfUrl={pdfUrl} /></div>
            <AppVersion />
            <Foot album={album} page={pages} pages={pages} />
          </div>
        </section>
      </article>
    </div>
  );
}

/** The facts of the day: date, landmarks reached, total time and place (the last two only for a finished run). */
function Facts({ album, light = false }: { album: Album; light?: boolean }) {
  const tz = album.time_zone;
  return (
    <ul className={light ? "qa-facts qa-facts--light" : "qa-facts"} aria-label="The day in numbers">
      <li><Icon name="calendar" />{formatDateFull(album.played_on, tz)}</li>
      <li><Icon name="flag" />{album.chapters.length} of {album.task_count} landmarks</li>
      {album.total_seconds !== null && <li><Icon name="clock" />{formatHms(album.total_seconds)}</li>}
      {album.rank !== null && (
        <li><Icon name="trophy" />{album.shared_rank ? "Shared " : ""}{ordinal(album.rank)} place</li>
      )}
    </ul>
  );
}

/** One line under the route: riddle minutes, penalty minutes, long breaks and the time on the clock, which
 *  add up to the total in the facts. Nothing for a run whose riddles were never timed. */
function RouteTotals({ album }: { album: Album }) {
  const timed = album.chapters.filter((chapter) => chapter.seconds !== null);
  if (timed.length === 0) return null;
  const riddles = timed.reduce((sum, chapter) => sum + (chapter.seconds ?? 0), 0);
  const penalties = album.chapters.reduce((sum, chapter) => sum + chapter.penalty_minutes, 0);
  const parts: [string, string][] = [["Riddles", formatHm(riddles)]];
  if (penalties > 0) parts.push(["Hints and reveals", `+${penalties} min`]);
  if (album.total_seconds !== null) {
    const breaks = album.total_seconds - riddles - 60 * penalties;   // pauses past the 5-minute grace (issue #49)
    if (breaks >= 60) parts.push(["Long breaks", `+${formatHm(breaks)}`]);
    parts.push(["On the clock", formatHm(album.total_seconds)]);
  }
  return (
    <p className="qa-route__sum" aria-label="Time in total">
      {parts.map(([label, value]) => <span key={label}>{label} <b>{value}</b></span>)}
    </p>
  );
}

/** The PDF: a real album is rendered and stored on the server (also kept for the host), so this is a
 *  download link. The preview has no server album and falls back to the browser's print dialog with the
 *  album's print stylesheet (A4, one sheet per page, no browser header or footer). */
function SavePdfButton({ pdfUrl }: { pdfUrl?: string }) {
  if (pdfUrl) {
    return (
      <a className="qc-btn qc-btn--gold qa-save" href={pdfUrl} download>
        <Icon name="download" />Download PDF
      </a>
    );
  }
  return (
    <button type="button" className="qc-btn qc-btn--gold qa-save" onClick={() => window.print()}>
      <Icon name="download" />Save as PDF
    </button>
  );
}

function ChapterSheet({ chapter, album, language, page, pages }: {
  chapter: AlbumChapter; album: Album; language: string; page: number; pages: number;
}) {
  const titleId = useId();
  const [first, ...rest] = chapter.photos;
  const landmark = pickText(chapter.landmark, chapter.landmark_i18n, language);
  return (
    <section className="qa-sheet qa-sheet--chapter" aria-labelledby={titleId}>
      <div className="qa-page">
        <header className="qa-chapter__head">
          <p className="qs-eyebrow">
            <Icon name="flag" />Landmark {chapter.number} of {album.task_count} · {formatTime(chapter.reached_at, album.time_zone)}
          </p>
          <h2 id={titleId} className="t-display-l qa-title">{landmark}</h2>
        </header>
        {first && <Photo photo={first} chapter={chapter} album={album} main />}
        {rest.length > 0 && (
          <div className="qa-photo-row">
            {rest.map((photo) => <Photo key={photo.url} photo={photo} chapter={chapter} album={album} />)}
          </div>
        )}
        <section className="qa-story" aria-label={`About ${landmark}`}>
          <p className="qs-eyebrow qs-eyebrow--gold"><Icon name="bulb" />About this place</p>
          <div className="qa-story__text"><Paragraphs text={pickText(chapter.story, chapter.story_i18n, language)} /></div>
        </section>
        <Foot album={album} page={page} pages={pages} />
      </div>
    </section>
  );
}

function Photo({ photo, chapter, album, main = false }: {
  photo: AlbumPhoto; chapter: AlbumChapter; album: Album; main?: boolean;
}) {
  const when = formatTime(photo.taken_at, album.time_zone);
  return (
    <figure className={main ? "qa-photo qa-photo--main" : "qa-photo"}>
      <img src={photo.url} alt={`${album.team} at ${chapter.landmark}, ${when}`} />
      <figcaption><Icon name="camera" />Team photo · {when}</figcaption>
    </figure>
  );
}

/** Running foot of an A4 sheet; hidden in the phone layout. */
function Foot({ album, page, pages }: { album: Album; page: number; pages: number }) {
  return (
    <footer className="qa-foot" aria-hidden="true">
      <span>{album.team} · {album.game}</span>
      <span>{page} / {pages}</span>
    </footer>
  );
}
