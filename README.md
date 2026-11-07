# Quest City Tour

## What it is

Quest City Tour is a mobile-first web app for guided city quests. An admin describes landmarks,
games and teams in YAML files. Each team gets a private link. Teams open the link on a phone and
work through a series of riddles:

- Answer the riddle (wrong answers are tolerated; hints and a "reveal" unlock over time or after
  enough attempts, at a time penalty).
- Walk to the landmark, take a team photo, and read its story.
- Finish all tasks (or run out of time) and see the results and the leaderboard.

Teammates on several phones share one run: if one phone solves a task, the others move on and show a
"teammate" toast.

The backend is FastAPI + SQLAlchemy (PostgreSQL, or SQLite for a quick local run) with blob storage
for photos and pictures (Azure Blob / Azurite, or plain files). The frontend is a React + Vite SPA.
The specs are in `specs/`, the design mocks in `frontend-mocks/`, and the look-and-feel proposals
(directions, variants, self-hosted fonts) in `design/` — open `design/index.html` in a browser.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package and interpreter manager)
- Python 3.12 (`uv` installs it for you). If no 3.12 interpreter can run on your machine, use
  Python 3.13 instead: `uv sync --python 3.13` (the code stays 3.12-compatible).
- Node 20+ (with npm)
- Docker (optional): provides PostgreSQL and Azurite. Without it, use the
  [no-Docker fallback](#no-docker-fallback).

## One-command dev run (no Docker)

```bash
./scripts/dev.sh
```

Runs the [no-Docker fallback](#no-docker-fallback) end to end in one foreground
terminal: it writes `backend/.env` (SQLite + local file storage, with a seeded
`ADMIN_DEV_EMAILS=admin@example.com`) on first run, installs dependencies,
migrates, runs `sync-config` (which prints the team game links), then starts
uvicorn and the Vite dev server together. The startup summary also prints the
admin panel URL and how to sign in for the active admin auth mode. Ctrl-C stops
both; every output line is tagged `[backend]` or `[frontend]` so the interleaved
logs stay readable.

Each run starts from a fresh SQLite database; `--keep-db` keeps the existing one.
`--auth password` runs the admin panel with e-mail and password sign-in for this
run (`ADMIN_AUTH_PROVIDER=password`). Unless you set `ADMIN_BOOTSTRAP_EMAIL` and
`ADMIN_BOOTSTRAP_PASSWORD` yourself, it seeds `admin@example.com` with the
throwaway password `dev-password-123`. `--auth entra` also needs the
`ADMIN_ENTRA_*` settings. Without `--auth`, the mode comes from the environment or
`backend/.env` (the default is the `dev` magic link). The script checks the
required settings before the setup steps run.

## Docker dev path

Start PostgreSQL 16 and Azurite from the repo root:

```bash
docker compose up -d
```

Set up and start the backend:

```bash
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run sync-config
uv run uvicorn questtour.main:create_app --factory --reload
```

`sync-config` reads `CONFIG_DIR` (default `config`, relative to `backend/`; the sample files live in
`backend/config/`).

`sync-config` validates the YAML files, writes new tokens into `teams.yaml`, loads everything into the
database and prints one game link per team, e.g.

```
Game links:
  The Explorers — Sofia Old Town Quest: http://localhost:5173/play/<token> (new)
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the printed link (the Vite dev server runs on port 5173 and proxies `/api` to the backend on
port 8000; set `DEV_API_TARGET` to proxy somewhere else).

## Production-like local run

Build the SPA and let FastAPI serve it:

```bash
cd frontend
npm run build          # creates frontend/dist
cd ../backend
```

Set these in `backend/.env` (or as environment variables):

```
STATIC_DIR=../frontend/dist
PUBLIC_BASE_URL=http://localhost:8000
```

Re-run `uv run sync-config` so the printed links use the new base URL, then start the server:

```bash
uv run uvicorn questtour.main:create_app --factory --port 8000
```

Open `http://localhost:8000/play/<token>`.

## No-Docker fallback

Without Docker, use SQLite and local file storage. Put this in `backend/.env`:

```
DATABASE_URL=sqlite:///./dev.db
HOST_ID=default
PUBLIC_BASE_URL=http://localhost:5173
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=.storage
CONFIG_DIR=config
```

Then run the same commands as in the Docker path (`uv sync`, `uv run alembic upgrade head`,
`uv run sync-config`, `uv run uvicorn ...`). Photos and pictures are written under
`backend/.storage/`. If Python 3.12 is not available, run `uv sync --python 3.13` first.

For the production-like variant, also set `STATIC_DIR=../frontend/dist` and
`PUBLIC_BASE_URL=http://localhost:8000`.

## Configuration reference

The admin configuration is three YAML files in the config directory plus an `images/` folder.

- `landmarks.yaml` — `landmarks:` list. Each has `id`, `name`, `task` (riddle text),
  `accepted_answers`, optional `hint1`, `hint2`, `tourist_info`, and optional pictures
  `task_picture` / `tourist_info_picture` (paths relative to the config directory, e.g.
  `images/task-domes.svg`). **`accepted_answers[0]` is the answer shown when a team reveals it.**
- `games.yaml` — `games:` list. Each has `id`, `name`, `time_zone`, `max_duration_minutes`,
  `reveal: { attempts, minutes, penalty_minutes }` (N attempts / X minutes before reveal unlocks,
  P penalty minutes), an `intro` text and `tasks:` (ordered landmark ids).
- `teams.yaml` — `teams:` (`id`, `name`, `participants`) and `assignments:` (`team`, `game`,
  `valid_from`, `valid_until`, `exit_message`). `token` fields are added by `sync-config`. An optional
  `service:` block (`team`, `name`) defines the service (test) team: `sync-config` writes one link per game
  under `service.tokens`.

Timestamps (`valid_from`, `valid_until`) **must be quoted** ISO-8601 strings, e.g.
`"2026-10-01T00:00:00"`. Without an offset they are read in the game's time zone.

### `sync-config`

```bash
uv run sync-config                              # validate, issue tokens, load into the database
uv run sync-config --validate-only              # validate the YAML only; change nothing
uv run sync-config --reissue TEAM_ID GAME_ID    # replace one team's token; the old link stops working
uv run sync-config --config-dir path/to/config  # override CONFIG_DIR
```

Warnings:

- `sync-config` writes the tokens into `teams.yaml`. **Commit `teams.yaml` after issuing tokens and
  keep the repository private** — the file holds live game links.
- Service (test) links are for testing only: they ignore every time limit, can be reset from the game
  screen and never appear on a leaderboard. Do not hand them to real teams.
- Game rule edits (max duration, N/X/P, validity windows) **apply live to running games**.
  Shortening them can end a game that is in progress. Only the landmark order of a running game is
  frozen.
- To swap two team names, rename one team through a temporary name in two `sync-config` runs
  (team names are unique, so a direct swap fails and rolls back).

## Deployment (Azure)

Production runs on Azure App Service, PostgreSQL Flexible Server and Blob storage. The infrastructure is
Terraform in `infra/`; GitHub Actions does the rest:

- **Pull requests** run CI: backend ruff and pytest (SQLite and PostgreSQL), frontend typecheck and
  vitest, static checks of the workflows, scripts and Terraform, and a build and smoke test of the
  deploy package.
- **Merge to `main`** re-runs CI and deploys to App Service through GitHub OIDC, once the repository
  variable `DEPLOY_ENABLED` is `true`. Commits that only touch `backend/config/`, `infra/`, `specs/`,
  `frontend-mocks/` or Markdown files never deploy. *Deploy* can also be run by hand, to redeploy or
  to roll back.
- **Infrastructure** changes go through the separate, manually run *Infrastructure (Terraform)*
  workflow: `plan`, then `apply` with `confirm = APPLY`.

- **Releases** are version tags on `main` (`v1.2.0`). Pushing one runs the *Release* workflow: it
  publishes a GitHub Release with generated notes and deploys that exact tag.

Build the deploy package locally with `bash scripts/package-app.sh dist/app.zip` (after
`npm run build` in `frontend/`) and check it with `bash scripts/smoke-package.sh dist/app.zip`.

### Which version is running

Every build carries its version, from `git describe`: the release tag (`v1.2.0`) when the build is a
release, `v1.2.0-3-g6dd4e31` for a `main` build three commits past it, or a bare commit hash before the
first tag. It is shown in the app footer (cover, welcome and finish screens, and the admin sidebar)
and reported by `GET /api/health` as `{"status": "ok", "version": "v1.2.0"}`; the deploy's smoke check
waits until production answers with the version it just shipped. The package carries it in a `VERSION`
file; `APP_VERSION` in the environment overrides it, and a dev checkout shows `development build`.

First-time setup, GitHub variables, day-2 operations and troubleshooting are in
[`infra/README.md`](infra/README.md).

## Tests

```bash
# Backend
cd backend
uv run pytest -q

# Optional: also run the PostgreSQL tests
TEST_DATABASE_URL=postgresql+psycopg://questtour:questtour@localhost:5432/questtour uv run pytest -q

# Frontend
cd ../frontend
npm test
```

Tests marked `postgres` are skipped unless `TEST_DATABASE_URL` points at PostgreSQL. Lint and type
checks: `uv run ruff check .` (backend), `npm run typecheck` (frontend).

## Photos and storage

Team photos are stored in the `photos` container as

```
photos/{Game}/{Team}/{timestamp}_{position}_{landmark}.{ext}
```

for example `photos/Sofia-Old-Town-Quest/The-Explorers/2026-10-03_14-05-09_01_Alexander-Nevsky-Cathedral.jpg`
(names are made file-safe; a same-second collision gets a `_2`, `_3`… suffix). With
`STORAGE_BACKEND=azure` against Azurite, browse them with
[Azure Storage Explorer](https://azure.microsoft.com/products/storage/storage-explorer) (connect to
the local emulator). With `STORAGE_BACKEND=local` they are plain files under `LOCAL_STORAGE_DIR`
(`ls -R backend/.storage/photos`).
