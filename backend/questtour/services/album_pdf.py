"""Render a memories album (issue #33) as an A4 PDF, mirroring the web album's print layout.

A patina cover with the facts of the day and the host's message, one page per landmark reached
(the team photo, further photos in a row, the story in two columns of small print), and a closing
summary page – the route with each riddle's minutes and a totals line – whose remaining height is a
collage of every photo. Set in Onest (OFL, bundled under
assets/fonts), so Cyrillic and Latin-extended text renders. Photos are decoded with Pillow (HEIC
included), cropped to their box, downscaled and re-encoded as JPEG so an album with ten 20 MB
originals stays a few megabytes.
"""

from __future__ import annotations

import io
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF, XPos, YPos
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from questtour.api.schemas import AlbumChapterOut, AlbumOut

register_heif_opener()

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Design tokens (frontend-mocks/ds/questcity/tokens.json), direction 02c "Evening Domes · Cards"
PATINA_800 = (15, 58, 44)
PATINA_600 = (31, 107, 79)
PATINA_300 = (127, 174, 149)
PATINA_50 = (221, 238, 228)
GOLD_700 = (111, 82, 16)
GOLD_500 = (207, 164, 60)
GOLD_300 = (230, 205, 134)
GOLD_100 = (248, 239, 211)
THEATRE_500 = (176, 74, 59)
INK = (15, 27, 22)
INK_MUTED = (63, 80, 72)
INK_INVERSE = (244, 241, 230)
SURFACE_SUNKEN = (223, 230, 223)
LINE = (195, 207, 197)

PAGE_W, PAGE_H = 210.0, 297.0
MARGIN = 20.0                 # the web album's print-safe margins (24 mm at the foot)
FOOT = 24.0
CONTENT_W = PAGE_W - 2 * MARGIN
MAX_PHOTO_PX = 1600
JPEG_QUALITY = 82

Images = Mapping[int, bytes]  # photo id -> original bytes


def _local(when: datetime, tz: str) -> datetime:
    return when.astimezone(ZoneInfo(tz))


def _hms(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _hm(seconds: int) -> str:
    """Whole minutes in words: '2 h 21 min', '1 h', '45 min' (the totals line; seconds would be noise)."""
    h, m = divmod(seconds // 60, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _facts(album: AlbumOut) -> list[str]:
    day = _local(album.played_on, album.time_zone)
    facts = [
        f"{day:%A}, {day.day} {day:%B %Y}",
        f"{len(album.chapters)} of {album.task_count} landmarks",
    ]
    if album.total_seconds is not None:
        facts.append(_hms(album.total_seconds))
    if album.rank is not None:
        facts.append(f"{'Shared ' if album.shared_rank else ''}{_ordinal(album.rank)} place")
    return facts


def prepare_photo(data: bytes, box_w: float, box_h: float) -> io.BytesIO | None:
    """Crop to the box's aspect ratio (centre), downscale, re-encode as JPEG. None if undecodable."""
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image) or image
        image = image.convert("RGB")
    except (OSError, ValueError):   # not an image we can read (Pillow's errors are OSError subclasses)
        return None
    w, h = image.size
    want = box_w / box_h
    if w / h > want:                       # too wide: trim the sides
        new_w = int(h * want)
        image = image.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
    elif w / h < want:                     # too tall: trim top and bottom
        new_h = int(w / want)
        image = image.crop((0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h))
    image.thumbnail((MAX_PHOTO_PX, MAX_PHOTO_PX))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    out.seek(0)
    return out


class _AlbumPDF(FPDF):
    def __init__(self, album: AlbumOut) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.album = album
        self.pages_total = len(album.chapters) + 2
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=FOOT)
        self.add_font("Onest", "", FONT_DIR / "Onest-Regular.ttf")
        self.add_font("Onest", "B", FONT_DIR / "Onest-Bold.ttf")
        self.set_title(f"{album.team} – {album.game} – memories album")
        self.set_author("Quest City Tour")
        self.foot_from_page = 2

    def footer(self) -> None:  # running foot on every page but the cover
        if self.page < self.foot_from_page:
            return
        self.set_y(-12)
        self.set_font("Onest", "B", 8)
        self.set_text_color(*INK_MUTED)
        self.cell(0, 5, f"{self.album.team} · {self.album.game}", new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.cell(0, 5, f"{self.page} / {self.pages_total}", align="R")

    # -- small building blocks --------------------------------------------------------------------

    def pill(self, x: float, y: float, text: str, fill, color, size: float = 8) -> float:
        """A rounded label like the web eyebrows; returns its width."""
        self.set_font("Onest", "B", size)
        w = self.get_string_width(text.upper()) + 6
        h = size * 0.6
        self.set_fill_color(*fill)
        self.rect(x, y, w, h, style="F", round_corners=True, corner_radius=h / 2)
        self.set_text_color(*color)
        self.set_xy(x + 3, y)
        self.cell(w - 6, h, text.upper())
        return w

    def skyline(self, x: float, y: float, w: float) -> None:
        """The Evening Domes mark, simplified: a row of domes and roofs in the palette."""
        u = w / 20
        base = y + 6 * u
        shapes = [  # (left in units, width, height, colour, dome?)
            (0.0, 1.6, 2.0, PATINA_600, True),
            (2.2, 1.6, 3.2, PATINA_600, True),
            (4.4, 3.2, 4.6, GOLD_500, True),
            (8.2, 4.6, 3.4, THEATRE_500, False),
            (13.4, 1.8, 2.0, PATINA_300, True),
            (15.8, 1.8, 2.4, GOLD_300, False),
            (18.2, 1.8, 2.6, PATINA_600, True),
        ]
        for left, width, height, colour, dome in shapes:
            self.set_fill_color(*colour)
            px, pw, ph = x + left * u, width * u, height * u
            if dome:
                self.rect(px, base - ph + pw / 2, pw, ph - pw / 2, style="F")
                self.ellipse(px, base - ph, pw, pw, style="F")
            else:
                self.rect(px, base - ph + 1.2 * u, pw, ph - 1.2 * u, style="F")
                self.polygon([(px, base - ph + 1.2 * u), (px + pw / 2, base - ph), (px + pw, base - ph + 1.2 * u)], style="F")

    def photo_box(self, images: Images, photo_id: int, x: float, y: float, w: float, h: float, caption: str) -> None:
        data = images.get(photo_id)
        prepared = prepare_photo(data, w, h) if data else None
        self.set_draw_color(*LINE)
        self.set_fill_color(*SURFACE_SUNKEN)
        self.rect(x, y, w, h + 6, style="DF", round_corners=True, corner_radius=3)
        if prepared is not None:
            self.image(prepared, x=x + 0.3, y=y + 0.3, w=w - 0.6, h=h - 0.6)
        self.set_font("Onest", "B", 7.5)
        self.set_text_color(*INK_MUTED)
        self.set_xy(x + 3, y + h)
        self.cell(w - 6, 6, caption)

    # -- pages ------------------------------------------------------------------------------------

    def cover(self) -> None:
        a = self.album
        self.add_page()
        self.set_fill_color(*PATINA_800)
        self.rect(0, 0, PAGE_W, PAGE_H, style="F")
        self.skyline(MARGIN, 30, CONTENT_W)
        self.set_xy(MARGIN, 82)
        self.set_font("Onest", "B", 9)
        self.set_text_color(*GOLD_300)
        self.set_char_spacing(1.4)
        self.cell(0, 6, "TEAM ALBUM", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_char_spacing(0)
        self.set_font("Onest", "B", 34)
        self.set_text_color(*INK_INVERSE)
        self.multi_cell(150, 14, a.game, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_font("Onest", "B", 11)
        chip_w = self.get_string_width(a.team) + 10
        self.set_fill_color(*GOLD_500)
        self.rect(MARGIN, self.get_y(), chip_w, 8, style="F", round_corners=True, corner_radius=2)
        self.set_text_color(*INK)
        self.set_xy(MARGIN + 5, self.get_y())
        self.cell(chip_w - 10, 8, a.team, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self.set_font("Onest", "B", 11)
        self.set_text_color(*GOLD_300)
        for fact in _facts(a):
            self.cell(0, 7, f"•  {fact}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # The host's message in a light card at the foot of the page
        self.set_font("Onest", "", 10)
        lines = self.multi_cell(CONTENT_W - 10, 5.5, a.host_message, dry_run=True, output="LINES")
        card_h = 5.5 * len(lines) + 20
        top = PAGE_H - MARGIN - card_h
        self.set_fill_color(*PATINA_50)
        self.rect(MARGIN, top, CONTENT_W, card_h, style="F", round_corners=True, corner_radius=3)
        self.pill(MARGIN + 5, top + 5, "From your host", GOLD_500, INK)
        self.set_font("Onest", "", 10)
        self.set_text_color(*INK)
        self.set_xy(MARGIN + 5, top + 13)
        self.multi_cell(CONTENT_W - 10, 5.5, a.host_message)

    def chapter(self, chapter: AlbumChapterOut, images: Images) -> None:
        a = self.album
        self.add_page()
        self.set_fill_color(255, 255, 255)
        y = MARGIN
        # Title row: the landmark and the badge
        badge = f"Landmark {chapter.number} of {a.task_count} · {_local(chapter.reached_at, a.time_zone):%H:%M}"
        self.set_font("Onest", "B", 8)
        badge_w = self.get_string_width(badge.upper()) + 6
        self.set_font("Onest", "B", 22)
        self.set_text_color(*INK)
        self.set_xy(MARGIN, y)
        self.multi_cell(CONTENT_W - badge_w - 6, 10, chapter.landmark, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        title_bottom = self.get_y()
        self.pill(PAGE_W - MARGIN - badge_w, y + 3, badge, PATINA_800, INK_INVERSE)
        y = title_bottom + 4
        # Photos: the first large, the rest in a row of three
        first, rest = chapter.photos[:1], chapter.photos[1:4]
        if first:
            photo = first[0]
            self.photo_box(images, photo.id, MARGIN, y, CONTENT_W, 84,
                           f"Team photo · {_local(photo.taken_at, a.time_zone):%H:%M}")
            y += 84 + 6 + 5
        if rest:
            gap, cols = 4.0, 3
            w = (CONTENT_W - gap * (cols - 1)) / cols
            for i, photo in enumerate(rest):
                self.photo_box(images, photo.id, MARGIN + i * (w + gap), y, w, 34,
                               f"Team photo · {_local(photo.taken_at, a.time_zone):%H:%M}")
            y += 34 + 6 + 5
        # The story, two columns of small print
        self.pill(MARGIN, y, "About this place", GOLD_500, INK)
        y += 9
        self.set_xy(MARGIN, y)
        self.set_font("Onest", "", 8.5)
        self.set_text_color(*INK)
        with self.text_columns(ncols=2, gutter=8, text_align="L", line_height=1.4) as cols:
            for i, paragraph in enumerate(p for p in chapter.story.split("\n\n") if p.strip()):
                with cols.paragraph(bottom_margin=3 if i else 0) as par:
                    par.write(" ".join(paragraph.split()))

    def fit(self, text: str, width: float) -> str:
        """`text` in the current font, shortened with an ellipsis if it would overflow `width`."""
        if self.get_string_width(text) <= width:
            return text
        while text and self.get_string_width(text + "…") > width:
            text = text[:-1].rstrip()
        return text + "…"

    def route(self, y: float) -> float:
        """The route in two columns, reading across: number, landmark, a gold dot per hint, the riddle's
        minutes and the time the team got there. Returns the y below the table."""
        a = self.album
        half = (CONTENT_W - 8) / 2
        row_h = 6.5
        rows = math.ceil(len(a.chapters) / 2)
        self.set_draw_color(*LINE)
        for i, chapter in enumerate(a.chapters):
            col, row = i % 2, i // 2
            x = MARGIN + col * (half + 8)
            ry = y + row * row_h
            self.line(x, ry, x + half, ry)
            self.set_font("Onest", "", 7.5)
            self.set_text_color(*INK_MUTED)
            self.set_xy(x, ry)
            self.cell(6, row_h, str(chapter.number))
            minutes = "" if chapter.seconds is None else f"{chapter.seconds // 60} min"
            self.set_font("Onest", "B", 8)
            minutes_w = self.get_string_width(minutes) + 2 if minutes else 0
            dots_w = 2.2 * chapter.hints
            name_w = half - 6 - 11 - minutes_w - dots_w
            self.set_text_color(*INK)
            self.cell(name_w, row_h, self.fit(chapter.landmark, name_w - 1))
            self.set_fill_color(*GOLD_500)
            for n in range(chapter.hints):
                self.ellipse(self.get_x() + 0.4 + 2.2 * n, ry + row_h / 2 - 0.65, 1.3, 1.3, style="F")
            self.set_x(self.get_x() + dots_w)
            self.set_text_color(*PATINA_600)
            self.cell(minutes_w, row_h, minutes, align="R")
            self.set_font("Onest", "", 7.5)
            self.set_text_color(*INK_MUTED)
            self.cell(11, row_h, f"{_local(chapter.reached_at, a.time_zone):%H:%M}", align="R")
        for col in range(min(2, len(a.chapters))):
            x = MARGIN + col * (half + 8)
            self.line(x, y + rows * row_h, x + half, y + rows * row_h)
        return y + rows * row_h

    def totals(self, y: float) -> float:
        """One centred line: riddle minutes, penalty minutes, long breaks and the time on the clock, which
        add up to the total in the facts. Returns the y below the line (unchanged if there is nothing)."""
        a = self.album
        timed = [c.seconds for c in a.chapters if c.seconds is not None]
        if not timed:
            return y
        riddles = sum(timed)
        penalties = sum(c.penalty_minutes for c in a.chapters)
        parts: list[tuple[str, str]] = [("Riddles ", _hm(riddles))]
        if penalties:
            parts.append(("Hints and reveals ", f"+{penalties} min"))
        if a.total_seconds is not None:
            breaks = a.total_seconds - riddles - 60 * penalties   # pauses past the 5-minute grace (issue #49)
            if breaks >= 60:
                parts.append(("Long breaks ", f"+{_hm(breaks)}"))
            parts.append(("On the clock ", _hm(a.total_seconds)))
        sep = "   ·   "
        width = 0.0
        for i, (label, value) in enumerate(parts):
            self.set_font("Onest", "", 7.5)
            width += self.get_string_width(label) + (self.get_string_width(sep) if i else 0)
            self.set_font("Onest", "B", 7.5)
            width += self.get_string_width(value)
        self.set_xy(MARGIN + (CONTENT_W - width) / 2, y + 2)
        for i, (label, value) in enumerate(parts):
            self.set_font("Onest", "", 7.5)
            self.set_text_color(*INK_MUTED)
            if i:
                self.cell(self.get_string_width(sep), 5, sep)
            self.cell(self.get_string_width(label), 5, label)
            self.set_font("Onest", "B", 7.5)
            self.set_text_color(*INK)
            self.cell(self.get_string_width(value), 5, value)
        return y + 7

    def closing(self, images: Images) -> None:
        a = self.album
        self.add_page()
        y = MARGIN
        self.set_font("Onest", "B", 8)
        self.set_text_color(*GOLD_700)
        self.set_char_spacing(1.4)
        self.set_xy(MARGIN, y)
        self.cell(CONTENT_W, 5, "THE END", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_char_spacing(0)
        self.set_font("Onest", "B", 20)
        self.set_text_color(*INK)
        self.cell(CONTENT_W, 10, a.team, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Onest", "", 10)
        self.set_text_color(*INK_MUTED)
        self.cell(CONTENT_W, 6, a.game, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Onest", "B", 9)
        self.set_text_color(*GOLD_700)
        self.cell(CONTENT_W, 7, "   ·   ".join(_facts(a)), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = self.get_y() + 2
        y = self.route(y)
        y = self.totals(y) + 4
        # The collage fills the rest of the page: three tiles per row, a lone last photo across the row
        photos = [(photo, chapter) for chapter in a.chapters for photo in chapter.photos]
        if not photos:
            return
        bottom = PAGE_H - FOOT - 4
        gap, cols = 3.0, 3
        n_rows = math.ceil(len(photos) / cols)
        tile_h = (bottom - y - gap * (n_rows - 1)) / n_rows
        tile_w = (CONTENT_W - gap * (cols - 1)) / cols
        for i, (photo, _chapter) in enumerate(photos):
            row, col = divmod(i, cols)
            left_in_row = len(photos) - row * cols
            span = cols if (left_in_row == 1 and col == 0) else (1.5 if left_in_row == 2 else 1)
            w = tile_w * span + gap * (span - 1)
            x = MARGIN + col * (tile_w + gap) if span == 1 else MARGIN + col * (tile_w * 1.5 + gap * 1.5)
            prepared = prepare_photo(images.get(photo.id, b""), w, tile_h)
            self.set_fill_color(*SURFACE_SUNKEN)
            self.rect(x, y + row * (tile_h + gap), w, tile_h, style="F", round_corners=True, corner_radius=2)
            if prepared is not None:
                self.image(prepared, x=x, y=y + row * (tile_h + gap), w=w, h=tile_h)


def render_album_pdf(album: AlbumOut, images: Images) -> bytes:
    pdf = _AlbumPDF(album)
    pdf.cover()
    for chapter in album.chapters:
        pdf.chapter(chapter, images)
    pdf.closing(images)
    pdf.pages_total = pdf.page  # a long story may have spilled onto a second page
    return bytes(pdf.output())
