"""Generate frontend/src/album/mock.ts from the sample landmarks.yaml: real landmark stories, dummy photos.

usage, from backend/ (its venv has PyYAML):
  uv run python ../scripts/album-mock.py config/landmarks.yaml config/games.yaml ../frontend/src/album/mock.ts
"""
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

landmarks_cfg = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
landmarks = {lm["id"]: lm for lm in landmarks_cfg["landmarks"]}
game = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))["games"][0]
order = game["tasks"]

# A Saturday morning walk: start 10:30 Sofia time (UTC+3 in October), 20–35 minutes per landmark, of which
# a 5-minute photo break (within the grace, issue #49) precedes every riddle but the first. One hint at the
# third landmark (+10 min) and a compass at the sixth (+5 min).
start = datetime(2026, 10, 3, 7, 30, tzinfo=UTC)
gaps = [28, 24, 35, 31, 22, 26]
photo_counts = [1, 2, 1, 3, 1, 2]
hints = [0, 0, 1, 0, 0, 1]
penalties = [0, 0, 10, 0, 0, 5]

chapters = []
t = start
photo_id = 0
for i, lm_id in enumerate(order):
    lm = landmarks[lm_id]
    gap = gaps[i % len(gaps)]
    t = t + timedelta(minutes=gap)
    reached = t
    riddle_minutes = gap if i == 0 else gap - 5
    photos = []
    for p in range(photo_counts[i % len(photo_counts)]):
        photo_id += 1
        taken = reached + timedelta(minutes=4 + 3 * p)
        photos.append({
            "id": photo_id,
            "url": f"https://picsum.photos/seed/{lm_id}-{p + 1}/1200/900",   # dummy photo for the design draft
            "taken_at": taken.isoformat().replace("+00:00", "Z"),
        })
    chapters.append({
        "number": i + 1,
        "landmark": lm["name"],
        "landmark_i18n": lm.get("name_i18n") or {},
        "story": lm["tourist_info"].strip(),
        "story_i18n": {code: text.strip() for code, text in (lm.get("tourist_info_i18n") or {}).items()},
        "reached_at": reached.isoformat().replace("+00:00", "Z"),
        "seconds": riddle_minutes * 60,
        "hints": hints[i % len(hints)],
        "penalty_minutes": penalties[i % len(penalties)],
        "photos": photos,
    })

end = t + timedelta(minutes=12)
album = {
    "game": game["name"],
    "team": "The Explorers",
    "time_zone": game.get("time_zone", "Europe/Sofia"),
    "played_on": start.isoformat().replace("+00:00", "Z"),
    "ended_at": end.isoformat().replace("+00:00", "Z"),
    "end_reason": "finished",
    "task_count": len(order),
    # R-7: riddle time + penalties; the photo breaks were all within the grace, so they cost nothing
    "total_seconds": sum(c["seconds"] for c in chapters) + 60 * sum(c["penalty_minutes"] for c in chapters),
    "rank": 2,
    "shared_rank": False,
    "host_message": "Thank you for exploring Sofia with us! Here is your journey, landmark by landmark – the "
                    "riddles you cracked, the stories behind the places, and the photos you took along the way.",
    "chapters": chapters,
}

body = json.dumps(album, ensure_ascii=False, indent=2)
out = f'''// Generated from backend/config/landmarks.yaml and games.yaml for the album design draft: the real landmark
// stories, a plausible Saturday-morning timeline, and dummy photos from picsum.photos (loaded only on
// the /album/preview page). Regenerate with scripts/album-mock.py; do not edit by hand.
import type {{ Album }} from "./types";

export const PREVIEW_TOKEN = "preview";

export const MOCK_ALBUM: Album = {body};
'''
Path(sys.argv[3]).write_text(out, encoding="utf-8")
print(f"wrote {sys.argv[3]}: {len(chapters)} chapters, {sum(len(c['photos']) for c in chapters)} photos")
