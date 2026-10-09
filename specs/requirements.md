# Quest City Tour — Requirements

> Status: **Reviewed** (2026-10-02). Technical design: [technical.md](technical.md).

## 1. Overview

**Purpose.** Give hosts a tool that lets their guests take a self-guided, gamified city tour. The route is a sequence of quests: solving the current quest unlocks the next location. At every landmark the team also takes and uploads a photo; the host later turns the photos into a surprise photo album for the team. Teams compete on a per-game leaderboard ranked by total time, penalties included.

**Users**

| Role | Description |
|---|---|
| Admin | Operator of the system. Defines landmarks, games, teams and assignments through configuration, and hands out game links. |
| Host | The organisation offering the tour to its guests. Browses and deletes the uploaded photos. |
| Player | A member of a team. Opens the game link on a phone and plays. No login. |

**Hosts.** v1 serves a single host organisation. The design must allow several independent hosts later: every landmark, game and team belongs to a `HostId`, and in v1 every record uses the same value.

**In scope for v1**
- A mobile-first web app that runs in a browser, in English.
- Landmarks, games, teams and assignments set up through configuration files.
- Hosting on Azure.

**Out of scope for v1**
- Admin panel / CMS. It is planned for a later stage, so the design must allow adding it without a rewrite.
- Native mobile apps, offline mode, maps/navigation, other languages, monitoring/alerting beyond basic logs.

## 2. Glossary and data model

| Term | Meaning |
|---|---|
| Landmark / Task | A place in the city plus the quiz task that leads to it. One landmark = one task. A landmark is defined once and can be used in many games, with the same riddle, hints, compass and answers everywhere. |
| Game | An ordered series of tasks with a unique identifier and its own leaderboard. |
| Team | A group of players who share one team identifier. |
| Assignment | A team assigned to a game. It carries the secret game link. |
| Game run | One team playing one game (at most one per assignment). It holds progress, timings, hints, reveals, attempts and photos. |
| Hint | Optional help for a task, with up to 2 per task. Each one adds a time penalty. |
| Compass | Optional directional pointer to a task's landmark. Opening it adds a time penalty. |
| Reveal | Giving up on a task: the answer is shown and a time penalty is added. |

**Relationships**
- Game ↔ Landmark: many-to-many. A game holds an ordered list of landmark IDs; a landmark can appear in many games.
- Team ↔ Game: many-to-many through Assignment. A team can take part in several games.

**Landmark / Task**

| Field | Notes |
|---|---|
| Landmark ID | Unique |
| Name | |
| Task picture | Optional picture shown with the task |
| Task | The question or riddle text |
| Accepted answers | A list of one or more strings (R-9) |
| Hint 1 | Optional |
| Compass | Optional; shows direction to the landmark when opened |
| Hint 2 | Optional; allowed only if Hint 1 is set |
| Tourist information | Shown after the task is completed |
| Tourist information picture | Optional |

**Game**

| Field | Notes |
|---|---|
| Game ID | Unique |
| Name | |
| Intro | Welcome text and rules shown before the start |
| Time zone | The city's time zone, e.g. `Europe/Sofia`; used for photo file names |
| Tasks | Ordered list of landmark IDs |
| Max duration | Maximum game duration, e.g. 4 h (R-8) |
| Reveal settings | N attempts, X minutes, P penalty minutes (R-6); defaults 5 / 20 / 30 |

**Team**

| Field | Notes |
|---|---|
| Team ID | Unique |
| Name | Unique within the host; shown on leaderboards and used in photo folder names |
| Number of participants | Information only, for the host's planning (e.g. album copies). Not enforced. |

**Assignment (Team ↔ Game)**

| Field | Notes |
|---|---|
| Team ID, Game ID | Unique pair |
| Access token | Secret, random, can be reissued (R-21). Generated automatically and stored in the YAML configuration, so the link can always be looked up and resent. |
| Valid from / Valid until | The link works only in this window |
| Exit message | Custom message shown with the leaderboard at the end of this game |

## 3. Game flow and rules

**Flow**
1. The admin defines a team and assigns it to a game.
2. The admin gives the team its game link (R-21).
3. Each team member opens the link and lands on the welcome page: game intro, rules, and the photo privacy notice.
4. Any player presses Start and confirms that the clock can't be paused. The game clock starts and the first task is shown on every team phone (R-18).
5. The team enters answers until one is correct (R-5, R-9), using hints (R-4) or revealing the answer (R-6) if needed.
6. The team uploads at least one photo taken at the landmark (R-10).
7. The team sees the tourist information about the landmark and continues.
8. Steps 5–7 repeat for each task in order (R-1).
9. When the last task is completed, the clock stops and the team's total time is recorded (R-7). After the last photo and landmark info, the team sees the finish screen: total time, leaderboard (R-12) and the exit message.

**Rules**
- **R-1 Order.** Tasks are played strictly in the order defined for the game. The next task is locked until the current one is completed (answered or revealed) and its photo is uploaded (exception: the service team, R-25).
- **R-2 Game clock.** The clock runs on wall-clock time. It starts when the first player presses Start and stops when the last task is completed (correct answer or reveal). It cannot be paused; walking, breaks and photo uploads all count. The server is the source of truth for time; the clock shown on phones is only a display of it.
- **R-3 Task timestamps.** For statistics, every task records *shown at* and *completed at*. Photo upload times are recorded separately and do not affect the score.
- **R-4 Hints.** Each task has up to 2 hints. Opening hint 1 adds **+10 min**; opening hint 2 adds a further **+15 min** (up to 25 min per task). Hint 2 is available only after hint 1 has been opened. Before a hint opens, a confirmation shows its penalty.
- **R-5 Wrong answers.** Teams can retry without limit, and wrong answers carry no penalty. Every attempt is logged for statistics.
- **R-6 Reveal answer.** A "Reveal answer" button unlocks after *N* wrong attempts or *X* minutes on the task, whichever comes first. Revealing shows the answer, adds a *P*-minute penalty on top of any hint penalties, and counts as completing the task. *N*, *X* and *P* are set per game (defaults 5, 20 min, 30 min). A confirmation shows the penalty first.
- **R-7 Total time.** Total time = (finish time − start time) + all hint penalties (including compasses) + all reveal penalties.
- **R-8 Maximum duration.** Each game sets a maximum duration, measured as wall-clock time since Start (penalties excluded). From 15 minutes before the limit, a warning shows the remaining time. When the limit is reached, or the assignment's validity window closes, the game ends unfinished: the team sees a "Time is up" screen with the exit message and the leaderboard, and does not appear on the leaderboard. Photos uploaded up to that point are kept. (Service links, R-25, have no time limit.)
- **R-9 Answer checking.** Players type the answer as free text. Before comparing, both the input and each accepted answer are normalised: lower-cased, leading/trailing/duplicate whitespace removed, punctuation removed, diacritics stripped. The answer is correct if it equals any accepted answer after normalisation. Checking happens on the server, so accepted answers are never sent to the browser.
- **R-10 Landmark photo.**
  - After a task is completed, the next task (or, after the last task, the finish screen) stays locked until at least one team member uploads a photo. There is no skip — except for the service (test) team (R-25), which may continue without a photo; uploading one remains possible.
  - Photos are not checked; any image is accepted. Team members can upload more than one photo per landmark; all are kept.
  - During the game, photos are visible only to the host. Players never see them in the app, not even a thumbnail: they are the surprise. After an upload, the app only confirms "Photo saved".
  - **Memories album (issue #33).** Once the run has ended (finished, or time is up), the app collects every photo the team took, with the landmark it belongs to and the landmark's information, into the team's memories album at `/album/{link token}`, reachable from the Finish and Time is up screens: a cover with the facts of the day, one page per landmark reached, and a closing summary. The album is also rendered as an A4 PDF, once, when the team (or the host) first asks for it, and stored for the host in the `albums` container; the team downloads that file. In the admin panel (Albums) the host can generate it ahead of time, download it, and delete it, after which the team's link no longer serves it until the host generates it again. Deleting a photo discards a stored album so the next request renders it without the photo.
  - Photos are stored at original resolution (no re-encoding) for print albums. The maximum upload size is 20 MB per photo.
  - The host browses the photos directly in storage (no UI in v1). They are organised per game and per team, with a timestamp in each file name:
    `{GameName}/{TeamName}/{yyyy-MM-dd_HH-mm-ss}_{TaskNo}_{LandmarkName}.{ext}`
    e.g. `Sofia-Center/The-Explorers/2026-10-14_11-32-05_03_Alexander-Nevsky.jpg`. Names are converted to safe file-name characters (Latin transliteration, spaces → `-`). The timestamp is the upload time in the game's time zone. If two uploads get the same name, a suffix `_2`, `_3`… is added.
  - Photos are kept until the host deletes them; there is no automatic deletion.
  - The welcome page tells players that photos are collected and kept by the host (a privacy notice).
- **R-11 Navigation.** The app shows no map, no distance and no directions. Finding the next landmark is part of the riddle. *Exception:* a team that has opened the compass (R-26) sees a direction arrow for the current task's landmark.
- **R-12 Leaderboard.** Each game has its own leaderboard, ranked by total time (R-7) with the lowest first.
  - Players see it only on the finish and "Time is up" screens, never during the game.
  - Only finished teams are listed.
  - Service (test) teams (R-25) are never listed.
  - Teams with equal total time (to the second) share a rank (e.g. 1, 2, 2, 4).
  - Each row shows rank, team name, total time (hh:mm:ss) and the number of hints used, counting opened hints *and* opened compasses. The viewing team's own row is highlighted.
- **R-13 One run per assignment.** Each team plays each assigned game once. Opening the link after the game has ended shows the finish (or "Time is up") screen again; the game cannot be replayed (except service links, R-25).

## 4. Screens

Mock-ups of every screen and state: [frontend-mocks/](../frontend-mocks/README.md).

| Screen | Content |
|---|---|
| Welcome | Game intro, rules, photo privacy notice, Start button. If the team has already started, players go straight to the current state. |
| Start confirmation | "Start the clock? It can't be paused. Every team member's phone will start too." Start / Cancel. Prevents one player starting the game for the whole team by accident. |
| Task | Task picture and text, answer input, hint buttons, compass button (when coordinates are set), reveal button (when unlocked), timer, progress bar. Wrong answers show a short "Not quite – try again". |
| Hint / Compass / Reveal confirmation | Shows the penalty and asks to confirm; then shows the hint, compass or the answer. |
| Photo upload | Take or choose a photo; "Photo saved" confirmation; retry on failure. |
| Landmark info | Tourist information, picture, Next riddle button (See results after the last task). |
| Finish | Total time, leaderboard, exit message, the team's average riddle rating and a word for the host (R-28), link to the memories album. |
| Time is up | Message that time ran out, exit message, leaderboard, the team's average riddle rating and a word for the host (R-28). |
| Link not valid | Shown for unknown or reissued tokens and outside the validity window. |
| 404 Not found | Shown for any URL that doesn't match a page in the app (e.g. a mistyped or truncated link). Friendly "Page not found" message telling players to open the exact link they received from the host. Shows no game data, and the server returns HTTP 404. |

**On every in-game screen**
- **R-14** The game timer (elapsed time, `hh:mm:ss`) is visible at all times. Next to it, the running penalty total (e.g. `+25 min`) is shown once any hint, compass or reveal penalty applies. In the last 15 minutes before the maximum duration (R-8), the timer switches to a warning style showing the remaining time.
- **R-15** A progress bar shows the current task out of the total.

## 5. Quality requirements

- **R-16 Mobile-first.** The design is responsive and mobile-first; the app is used mainly on phones in current iOS Safari and Android Chrome.
- **R-17 Session persistence.** If a player closes the browser by mistake, reopening the game returns them to their current progress.
- **R-18 Shared team progress.** Game progress is recorded on the server. Every team member who opens the game sees the current task and state. All team members are equal:
  - Any member can start the game, answer, open a hint, open a compass, reveal an answer or upload a photo. The action applies to the whole team.
  - The first correct answer (or reveal) completes the task, and later submissions for that task are ignored.
  - Each hint, compass or reveal is charged to the team at most once per task, even if several members press it at the same moment.
  - The other phones show the new state (next task, opened hint, etc.) within **1 minute**. A phone also refreshes straight away whenever its player acts (answer, hint, reveal, upload) and when the app comes back to the foreground. An action on a task the team has already completed is rejected, and the phone moves to the current task. When a phone moves on because of a teammate's action, it shows a short notice (e.g. "A teammate solved this task").
- **R-19 Platform.** v1 is a website used in a mobile browser; no installation is needed.
- **R-20 Extensibility.** The data model and backend must allow a CMS and multiple hosts to be added later without a rewrite.
- **R-21 Access.** Each assignment has its own secret link containing a long random token (at least 128 bits, not guessable). Players do not log in; anyone with the link plays as that team.
  - The link works only between the assignment's *valid from* and *valid until* dates (except service links, R-25).
  - The admin can reissue the token, which immediately makes the old link stop working.
  - Each browser gets an anonymous device ID (stored locally) so the number of devices that joined a game run can be counted.
  - v1 has no admin login; admin work is done through configuration (see technical.md).
- **R-22 Language.** v1 is in English only: the interface and all content.
- **R-23 Weak signal.** When the connection drops, the app shows "No connection – retrying…" and retries automatically. A failed photo upload can be retried without retaking the picture, because the selected photo is kept until the upload succeeds. No full offline mode.
- **R-24 Scale.** v1 targets a few teams per day, with at most about 10 game runs at the same time.
- **R-25 Service (test) team.** `teams.yaml` may define one service team. `sync-config` gives it one link per
  game, automatically for every game. Its links ignore the validity window, the maximum duration and the
  reveal waiting time (reveal is available as soon as a task is shown; penalties are still charged), and the
  photo is optional: the team may continue to the next task without uploading one (R-1, R-10). The game
  screen shows a "Reset test run" button that deletes the run with its answers and photos, so the link starts
  again from the beginning. Service runs never appear on any leaderboard.
- **R-26 Compass.** Each task can offer a compass that shows the direction from the team to the task's landmark. Opening it adds **+5 min**. Before it opens, a confirmation shows the penalty. Once opened, it stays visible until the task is completed; it is charged at most once per task. It does not carry over to the next task.
- **R-27 Compass availability.** The compass is available as soon as the task is shown. A landmark without coordinates has no compass; the button is hidden.
- **R-28 Riddle rating and feedback.** Right after a riddle is solved or revealed, each phone may rate it with one to five stars; the rating is optional, free of penalty, changeable, and one per phone per riddle. The Finish and Time is up screens show the team's average over all its ratings with their count, and let each phone send one comment to the host once the game is over. The host sees, in the admin panel, every riddle's average across all teams and the teams' comments. Ratings and comments never change the game state or its version.
