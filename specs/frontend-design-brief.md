# Quest City Tour — Frontend Design Brief

> Purpose: instructions for producing screen mock-ups of the player app. Derived from [requirements.md](requirements.md) (rule numbers R-n refer to it). This brief stands on its own; no other document is needed to design the screens.
>
> Mocks: [frontend-mocks/](../frontend-mocks/README.md), built with the Quest City Tour design system (https://claude.ai/artifact/EZorDtth41MxdkBwtkt8CP).

## 1. Product in one paragraph

Quest City Tour is a self-guided, gamified city walking tour played in a phone browser. A team of friends or colleagues gets one link. Each step shows a riddle; solving it reveals which landmark to walk to. At the landmark the team takes a photo, reads short tourist facts, and unlocks the next riddle. A clock runs from start to finish, hints and giving up cost penalty minutes, and at the end the team sees its place on the game's leaderboard. The photos are never shown back to players: the host later turns them into a **surprise photo album**.

## 2. Who uses it and where

- **Players:** tourists and team-event participants of any age; not necessarily tech-savvy; English-speaking (the app is English only).
- **Device:** a phone, held in one hand, often while walking. Current iOS Safari and Android Chrome.
- **Setting:** outdoors, often bright sunlight, glare, noise, a weak mobile signal, short attention spans between landmarks.
- **Team:** several team members may have the game open on their own phones at the same time; all see the same state.
- **No login.** The link is the only way in.

## 3. Design goals

1. **Readable outdoors.** High contrast, large type (body ≥ 16 px; answer input ≥ 16 px so iOS doesn't zoom), no low-contrast greys for important text. Light theme.
2. **One-handed.** Primary actions sit in the bottom half of the screen; tap targets ≥ 44 × 44 px.
3. **Playful but clear.** It should feel like an adventure/quest, not a form, but rules, penalties and the timer must never be ambiguous.
4. **Penalties are always explicit.** Every action that costs time shows the cost before the player confirms.
5. **Calm under poor signal.** Connection problems are shown gently and recover on their own.

No brand identity is defined yet. Propose a visual direction (colour palette, type, icon style) that fits a city adventure, and keep it easy to re-brand per host later (logo and accent colour swappable).

**Chosen direction (October 2026): 02c "Evening Domes · Cards"** from the proposals in [`design/`](../design/index.html): deep patina bands (header, hero, finish) with a thin gold rule, a light sage reading surface, raised white cards for riddle / hints / rules / leaderboard, sunken flat controls, solid gold penalty chips, a progress bar segmented per task, filled icons, and Onest + JetBrains Mono (self-hosted, full Cyrillic). Token values live in `frontend-mocks/ds/questcity/tokens.json`; the mock-ups in `frontend-mocks/` predate this direction and remain the reference for layout and states, while `design/02c-evening-cards.html` is the reference for look and feel.

## 4. Layout frame

- Design at **390 × 844** (iPhone 14/15) as the primary frame; check that nothing breaks at **360 × 740** (small Android).
- Portrait only.

**Persistent in-game header** (on every screen from Start until the last landmark's info; R-14, R-15). The Finish and Time is up screens have no header: the clock has stopped, and they show the final totals instead.
- **Timer**: elapsed time `hh:mm:ss`, always visible, ticking.
- **Penalty total** next to the timer, e.g. `+25 min`, shown once any penalty exists.
- **Progress**: `Task 3 of 8` plus a progress bar.
- **Time warning state**: in the last 15 minutes before the game's maximum duration, the header switches to a warning style and shows the remaining time, e.g. `12:40 left` (R-8).
- **Language pill** (only when the game has translations, issue #6): a ghost pill with a globe and the language code (`EN`) at the right end of the top row. It opens a bottom sheet that lists the languages by their own names (`English`, `Deutsch`, `Srpski`) with the current one ticked; a tap picks and closes. The cover and the welcome hero, which have no header, carry the same pill in the same top-right corner, so the control never moves between screens. Finish and Time is up have nothing to translate and no pill.

**Memories album** (issue #33, outside the game): once the run has ended, the team's photos and the landmark
information come together at `/album/{token}` (the game link's token; the Finish and Time is up screens link
to it with "Open your memories album"; until the run ends the page says the album isn't ready). An A4
document, not a game screen, with the same language pill as the game for the stories: a patina cover sheet with
the skyline, "Team album", the game name, the team chip, the facts of the day (date, landmarks reached, total
time, place) and the host's message; one sheet per landmark reached – `Landmark 3 of 6 · 11:42`, the
landmark name, the team photo(s) with the time they were taken (first one large, the rest in a row of three)
and what the place is, in two columns of small print (the riddles are not repeated); and a closing sheet with
a contact sheet of every photo. Pages keep 20 mm margins (24 mm at the foot) so no printer cuts the text.
On a desktop the sheets show as true A4 pages; on a phone they flow as cards. Text may be selected and
copied. "Save as PDF" opens the print dialog with A4 pages and no browser header. Until the album API
exists, `/album/preview` renders a mock album with dummy photos.

**Riddle rating and a word for the host** (R-28, issue #38): on Correct and Revealed, a white card "Rate this
riddle" with five 48 px stars; a tap saves the rating at once and the stars turn gold, with a word for the
score (Too hard or unclear, Not great, It was OK, Good one, Loved it!); nothing blocks the photo button. On
Finish and Time is up, after the host's message: a card "Your riddle ratings" with the team's average as a
big number next to partially filled stars and "from N ratings" (or a line saying the team didn't rate), and
a card "A word for your host" with a text box and "Send to your host", replaced by a thank-you once this
phone has sent its comment.

**Connection banner** (any screen, R-23): a slim banner `No connection – retrying…`, which disappears automatically when the connection is back.

## 5. Screens to mock

For each screen, the states listed must be mocked as separate frames.

### 5.0 Cover
The first screen of a team link while the game has not started: a full-screen patina band with the skyline illustration, the kicker ("A city quest in N riddles"), the game name, the team name and a single gold button, **How it works**, which opens the Welcome screen. No clock, no rules, no network call; shown once per page load. Players who open the link after the game has started land on the current state instead.

### 5.1 Welcome
Shown after the cover, when a player opens the team link before the game starts.
- Game name and intro text (a few paragraphs, admin-provided).
- Rules summary: tasks are played in order; the clock runs without pause from Start; hint 1 = +10 min, hint 2 = +15 min; giving up on a task = +30 min (number set per game); a photo is required at every landmark.
- **Photo privacy notice** (short, plain): photos you upload are collected and kept by the host.
- Primary button: **Start the quest**.
- States: *default*. (If the team has already started, players skip this screen and land on the current state, so no extra frame is needed.)

### 5.2 Start confirmation
- Modal: "Start the clock? It can't be paused. Every team member's phone will start too."
- Buttons: **Start** / Cancel.

### 5.3 Task
The main screen; players spend most of their time here.
- Optional task picture (may be absent; design both).
- Riddle text (from one line up to ~6 lines).
- Answer input (free text) + **Submit** button.
- Hint buttons: **Hint 1 (+10 min)**, **Hint 2 (+15 min)**. Hint 2 is disabled until hint 1 is opened. A task may have 0, 1 or 2 hints.
- **Reveal answer (+30 min)** button: hidden or clearly locked until it unlocks (after 5 wrong attempts or 20 minutes on the task, per game). It should be less prominent than Submit.
- Opened hints stay visible on the task screen, labelled with their penalty.
- States:
  1. Default, with picture.
  2. Default, without picture.
  3. Wrong answer: inline "Not quite – try again", input keeps the text.
  4. Hint 1 opened.
  5. Both hints opened.
  6. Reveal answer unlocked.
  7. Time warning active in the header.
  8. Offline banner shown.
  9. Updated by a teammate: a short toast such as "A teammate solved this task" when the screen moves on because of another phone.

### 5.4 Hint confirmation (modal)
- "Open hint 1? This adds 10 minutes to your time." → **Open hint** / Cancel.
- Same for hint 2 with +15 min.

### 5.5 Reveal confirmation (modal) and revealed answer
- "Give up and reveal the answer? This adds 30 minutes to your time." → **Reveal** / Cancel.
- Then a revealed-answer state: shows the answer and a **Continue** button that leads to the photo step.

### 5.6 Correct answer
- Short celebratory moment (e.g. a check mark or confetti), then the landmark name and **"Take a photo, create a memory"** call to action. This can be a screen or a transition state.

### 5.7 Photo upload
- Prompt: "Take a photo of your team at {Landmark name}." Players can take a new photo with the camera or choose one from the gallery. More than one photo is allowed.
- **Important:** the app must **not** show a preview or thumbnail of the photo (it is a surprise album). After choosing, show only a neutral "1 photo ready" or similar, never the image.
- The way forward (Continue) is locked until at least one photo is saved; there is no skip — except for the service (test) team (R-25), whose Continue is enabled without a photo.
- States:
  1. Prompt (nothing uploaded yet).
  2. Uploading, with a progress indicator.
  3. Saved: "Photo saved ✓", with buttons **Add another photo** and **Continue**.
  4. Failed: "Upload failed – check your connection", with a **Retry** button (no need to retake the photo).

### 5.8 Landmark info
- Landmark name, a picture, tourist information text (can be several paragraphs, so scrolling is expected).
- Button: **Next riddle**, or **See results** after the last task.

### 5.9 Finish
- Celebration headline, e.g. "You did it!"
- The team's total time, with a breakdown: elapsed time + hint penalties + reveal penalties = total.
- **Leaderboard** for this game (R-12): rank, team name, total time `hh:mm:ss`, hints used. The player's own team row is highlighted. Teams with equal time share a rank (e.g. 1, 2, 2, 4). It can be long (scrolls). Only finished teams appear.
- **Exit message** from the host (custom text, 1–3 sentences), e.g. a thank-you and a hint that a surprise is coming.
- No "play again" action. Reopening the link later shows this same screen.

### 5.10 Time is up
Shown when the game's maximum duration is reached or the link's validity ends.
- Friendly, non-punishing message: "Time's up! Thanks for playing."
- Tasks completed, e.g. `5 of 8`.
- The team is **not** on the leaderboard; show the leaderboard anyway, without the team's row.
- The host's exit message.

### 5.11 Link not valid
For a link that's expired, not yet active, or replaced.
- Message: "This game link isn't active. Please contact your host for a valid link."
- If useful, distinguish "not started yet – opens on {date}" from "expired". No game data is shown.

### 5.12 404 Not found
For any address that isn't a page in the app.
- "Page not found. Please open the exact link you received from your host."
- No game data; no navigation into the game.

### 5.13 Loading
- A loading state for the first open of a link (fetching the game state). Use a skeleton or a simple branded spinner.

## 6. Sample content for the mocks

Use realistic content, not lorem ipsum.

- **Game:** "Sofia Old Town Quest", 8 tasks, max duration 4 h.
- **Team:** "The Explorers".
- **Riddle example:** "Golden domes shine over the square that bears my name. I was built to honour soldiers who fell for this land's freedom. Who am I?"
- **Accepted answer (shown only when revealed):** "Alexander Nevsky Cathedral".
- **Hint 1:** "Look for the largest golden domes in the city centre."
- **Hint 2:** "The cathedral is named after a Russian saint and prince."
- **Tourist info:** 2–3 short paragraphs about the cathedral (built 1882–1912 in memory of the soldiers who died in the Russo-Turkish War of 1877–78, which led to Bulgaria's liberation; one of the largest Eastern Orthodox cathedrals in Europe).
- **Timer examples:** `01:12:45` elapsed, `+25 min` penalties; warning state `3:47:20` with `12:40 left`.
- **Leaderboard sample:**

| Rank | Team | Total time | Hints |
|---|---|---|---|
| 1 | Night Owls | 02:41:05 | 1 |
| 2 | The Explorers | 02:58:30 | 3 |
| 2 | Map Breakers | 02:58:30 | 2 |
| 4 | Sunny Side | 03:20:12 | 5 |

- **Exit message:** "Thank you for exploring Sofia with us! Keep an eye on your inbox – a little surprise from your journey is on its way."

## 7. Out of scope for the mocks

- Admin or host screens (there are none in v1).
- Maps, directions or navigation (finding the place is part of the riddle).
- Any view of uploaded photos.
- UI languages other than English (riddle and landmark content can be translated; see the language pill in §4).
- Desktop layouts (the app should still be usable on desktop, but no separate design is needed).
