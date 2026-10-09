# Contributing to Quest City Tour

Thanks for helping build Quest City Tour. This guide explains how to work in this repo: what the
specs mean for you, how to set up a dev environment, and what to check before opening a pull
request.

## Read the specs first

The files in `specs/` are the contract for how the app behaves. **Requirements are numbered R-1 …
R-23** and code comments, tests and UI copy reference those IDs.

- `specs/requirements.md` — what the app must do (game flow, rules, screens)
- `specs/technical.md` — architecture, Azure hosting, configuration, deployment
- `specs/frontend-design-brief.md` — the player-facing UI, section §5 maps 1:1 to screens

If you change behaviour, update the spec in the same change. If code and spec disagree, the spec
wins — fix the code (or propose a spec change explicitly).

## Non-negotiable invariants

These come from the requirements; a pull request that breaks them is wrong even if tests pass:

1. **The server is the source of truth.** Clock, answer checking, penalties, timeouts and game flow
   are computed server-side; the browser only displays state. No game logic in the frontend.
2. **Accepted answers never leave the server.** Answer checking (R-9) happens in
   `backend/questtour/normalize.py` and services; no API response ever includes the answer payload.
3. **Access tokens (R-21)** are ≥128 bits, URL-safe; the database stores only a hash and the
   plaintext lives only in `backend/config/teams.yaml`.
4. **Concurrency (R-18):** answer / hint / reveal / photo actions lock the game run row in one
   transaction — first correct answer wins, each penalty is charged exactly once. Teammates sync by
   60 s polling; no WebSockets in v1.
5. **One run per assignment (R-13):** a game can never be replayed — except service (test) links (R-25), which can
   be reset from the game screen.
6. **Photos (R-10):** stored at original resolution, never re-encoded, max 20 MB,
   JPEG/PNG/HEIC/WebP; players never see photos, not even thumbnails.
7. **Real 404s:** the SPA is served only for known routes (`backend/questtour/web.py`); anything
   else returns an HTTP 404.
8. **Extensibility (R-20):** keep `host_id` on every config table (v1 uses one value) and keep the
   database — not YAML — as the runtime source of data, so a CMS can be added later.
9. **Python 3.12 compatibility:** production runs 3.12; don't use 3.13+-only stdlib features.

## Getting set up

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Node 20+, Docker (optional).

```bash
# 1. Infrastructure (PostgreSQL 16 + Azurite) — optional
docker compose up -d

# 2. Backend
cd backend
cp .env.example .env          # defaults match docker-compose
uv sync                       # use `uv sync --python 3.13` if 3.12 isn't available
uv run alembic upgrade head
uv run sync-config            # validates YAML, seeds DB, prints game links
uv run uvicorn questtour.main:create_app --factory --reload

# 3. Frontend (second terminal)
cd frontend
npm install
npm run dev                   # :5173, proxies /api to :8000
```

No Docker? Use the SQLite + local-file fallback from `README.md` ("No-Docker fallback").

## How to verify your changes

Run both test suites and both checkers before opening a PR:

```bash
# backend (from backend/)
uv run pytest -q
uv run ruff check .                                  # lint, line-length 100

# with the PostgreSQL tests too (needs docker compose up)
TEST_DATABASE_URL=postgresql+psycopg://questtour:questtour@localhost:5432/questtour \
  uv run pytest -q

# frontend (from frontend/)
npm test
npm run typecheck
```

All of these must pass. There is no staging environment; `main` is what gets deployed.

### Test conventions

- Backend tests live in `backend/tests/`, seeded via `seed_game` from `tests/factories.py`. Drive
  time with the `clock` fixture (`clock.advance(minutes=…)`); never call `datetime.now()` in
  services — everything takes the injected clock.
- Postgres-only tests (e.g. `test_concurrency_pg.py`) are marked `postgres` and skipped unless
  `TEST_DATABASE_URL` is set.
- Frontend tests are vitest, colocated with the source (`*.test.ts(x)`); game-state fixtures come
  from `src/test/fixtures.ts`.
- Screens have per-screen test files covering the states shown in the mock-ups (wrong answer, hints,
  reveal unlocked, time warning, offline banner, teammate toast, …).

## Working on the frontend

- Follow the mock-ups in `frontend-mocks/` (`<Screen>.dc.html`, openable in a browser) and the
  brief's §5 screen list. `frontend-mocks/README.md` maps every screen and state to its file.
- Build at **390 × 844** first; verify nothing breaks at **360 × 740**. Portrait only.
- Use the design system: component classes `qc-*` (`src/styles/questcity.css`) and screen layout
  classes `qs-*` (`src/styles/quest-screens.css`), tokens from
  `frontend-mocks/ds/questcity/tokens.json`. Every colour/size must read a CSS token — no raw
  values.
- Every interactive element gets the 3px focus ring; penalties are always shown before they are
  paid.
- Routing between screens is the pure function `src/game/selectScreen.ts`; keep it pure and tested.
  Screens themselves stay dumb-ish; `src/game/useGame.ts` owns polling, offline handling, teammate
  toasts and the `act()` / `track()` wrappers.
- Frontend types in `src/api/types.ts` mirror `backend/questtour/api/schemas.py` — change them
  together.

## Backend conventions

- Layering: `api/` (HTTP + Pydantic schemas) → `services/` (business logic and invariants) →
  `models.py` / `db.py` / `storage.py`. Keep business rules out of routers.
- All settings come from environment variables (`.env` locally, `.env.example` is the reference;
  App Service app settings in Azure). No hard-coded configuration.
- YAML config timestamps must be quoted ISO-8601 strings; without an offset they are read in the
  game's time zone.

## Secrets and configuration

- `backend/.env` is git-ignored. Never commit it.
- `backend/config/teams.yaml` holds **live game links** after a `sync-config` run. It must be
  committed (this repo is private), but never copy tokens into code, tests, logs or issue text.
- **Config changes are applied to production by hand, not by deploy.** `backend/config/` is never
  part of the deploy package (it holds live token files), and the app only seeds an empty database,
  so edits to `landmarks.yaml` / `games.yaml` (translations, game rules, validity windows) reach the
  production database only when someone runs `sync-config` against prod — infra/README.md,
  first-time setup step 8, using its `admin_sync_config_env` output. A missed sync shows up as
  silently missing data, not an error: the language menu did not appear because the new translations
  were in the repo but never synced. Commit `teams.yaml` after the run if it changed.
- Game rule edits (max duration, reveal N/X/P, validity windows) **apply live to running games**;
  only a run's landmark order is frozen. Consider in-progress games when touching config handling.
- `accepted_answers[0]` is the answer shown when a team reveals it — order matters.

## Opening a pull request

1. Branch from `main`; keep changes focused and the specs updated in the same PR.
2. Make sure every numbered rule your change touches still holds (see "Non-negotiable invariants").
3. Run the full verification list above; note anything you could not run (e.g. Postgres tests
   without Docker) in the PR description.
4. PRs target `main`. A reviewer checks spec compliance, layering (`api/` → `services/` → data),
   and that both suites pass.

## Releasing

Every merge to `main` deploys, so a release is a name for the state of `main` at a point in time:
an annotated tag `vMAJOR.MINOR.PATCH` on a `main` commit.

```bash
git checkout main && git pull
git tag -a v1.2.0 -m "v1.2.0"
git push origin v1.2.0
```

Pushing the tag runs the *Release* workflow, which publishes a GitHub Release with generated notes
and deploys exactly that tag, so the footer and `GET /api/health` report `v1.2.0` rather than the
`v1.1.0-7-gabc1234` build number the merge before it produced. Bump MAJOR for a change players or
hosts must adapt to, MINOR for new features, PATCH for fixes. Tag only on `main`; the workflow
refuses a tag it cannot reach from there.

## Where to ask questions

The specs are authoritative — start there. For anything the specs don't cover, open an issue or
discuss it in the PR before implementing, especially for changes to game flow (R-1 … R-12) or
security-relevant behaviour (R-9, R-10, R-21).
