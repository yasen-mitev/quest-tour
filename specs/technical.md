# Quest City Tour — Technical Specification

> Status: ready for review. Companion to [requirements.md](requirements.md).

## 1. Constraints

- Hosting on **Azure**, using Azure-native components for the web app, database, storage and roles.
- v1 is a browser-based website; there are no native apps.
- v1 configuration comes from files (section 4); the admin panel and its sign-in are described in section 3.
- Expected scale for v1 is small: a few teams per day and at most about 10 game runs at the same time. The design must still allow multiple hosts and a CMS to be added later.

## 2. Architecture

```
Phone browser (React SPA)
        │  HTTPS / JSON
        ▼
Azure App Service (Linux)  ── Python FastAPI: REST API + serves the React build
        │                         │
        ▼                         ▼
Azure Database for         Azure Storage Account
PostgreSQL Flexible Server (Blob container "photos")
```

| Component | Azure service | Notes |
|---|---|---|
| Frontend | React SPA (TypeScript, Vite), built and served as static files by the backend | Mobile-first |
| Backend | Python 3.12 + FastAPI on **Azure App Service** (Linux, B1 plan) | Single deployable unit; always on, no cold starts |
| Database | **Azure Database for PostgreSQL Flexible Server** (Burstable B1ms) | Configuration and runtime state |
| Photos | **Azure Storage Account**, Blob container `photos` | Original files; the host browses them with Azure Storage Explorer or the Portal |
| Identity | **Managed identity** for App Service → PostgreSQL and Blob; **Entra ID + Azure RBAC** for people | No secrets in code |
| Secrets | App Service app settings, fed from `sensitive` Terraform variables (`TF_VAR_*`) that the Infra workflow reads from GitHub secrets | There is no Key Vault in v1 |

Estimated cost: about €25–40/month (to be confirmed in the Azure pricing calculator).

## 3. Key design decisions

- **Server is the source of truth.** Game state, the clock (R-2, R-8), answer checking (R-9) and penalties are all calculated on the server. The browser only displays them.
- **Concurrency.** Answer, hint, reveal and photo actions run in a database transaction that locks the game run row. This guarantees "first correct answer wins" and "each penalty charged once" (R-18).
- **Team sync by polling.** Each phone fetches the game run state every **60 seconds**, and also immediately after its own action and when the page becomes visible again (R-18). No real-time service (SignalR/WebSockets) is needed in v1.
- **Session persistence.** The access token in the URL identifies the assignment, and the browser stores the token and an anonymous device ID in `localStorage`. Reopening the page reloads the state from the server (R-17).
- **Access tokens.** At least 128 bits of randomness, URL-safe. The issued token is stored in plain text in the YAML configuration (section 4), so the admin can always look up and resend a team's link. The database stores only a hash of it. Requests outside the validity window or with a reissued token get a friendly "Link not valid" page (R-21).
- **Accepted answers are never sent to the client.**
- **404 handling.** FastAPI serves the React app only for known routes (e.g. `/`, `/play/{token}`). Any other path gets the 404 page with a real HTTP 404 status, not the usual single-page-app fallback that returns 200.
- **Time limits are enforced on the server.** The maximum duration and validity window (R-8) are checked on every request, so the game ends correctly even if no phone is open.
- **Multi-host readiness.** Every configuration table has a `host_id` column (R-20); v1 uses a single value.
- **Admin sign-in.** The admin panel (`/admin`, API under `/api/admin`) signs in with e-mail and password by default. `ADMIN_AUTH_PROVIDER` selects one of three modes: `dev` (local magic link for `ADMIN_DEV_EMAILS`; the Python default, rejected in production), `password` (the Terraform default) and `entra` (password **and** Microsoft Entra sign-in, for upgraded legacy deployments). Admins live in the `admin_users` table (e-mail, argon2id password hash); runtime switches live in the `app_settings` table, currently the Entra on/off toggle. Entra can be enabled later from the Administrators screen if the `ADMIN_ENTRA_*` settings are configured; they are required only in `entra` mode. The first admin is seeded from `ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` (12 characters or more) on first start only. After that the database owns the password, and the recovery CLI is `admin-password --email <e-mail>`.
  - `POST /api/admin/auth/password` signs in with e-mail and password (throttled in memory, per instance). `GET /api/admin/auth/provider` tells the login screen which sign-ins to offer; `login`, `callback` (Entra), `magic/request` and `magic/verify` (dev) and `logout` complete the set.
  - `/api/admin/account/*` serves the signed-in admin: `auth-settings` (read the session provider, the signed-in e-mail and the Entra toggle, change the toggle), `password` (change own password), and `admins` (list, add, delete, and set another admin's password).
  - The admin SPA's **Administrators** screen (`/admin/administrators`) is the UI for those endpoints: the list of administrators, Change my password, and the sign-in methods. A password change does not invalidate other sessions.

## 4. Configuration

- Configuration lives as YAML files in the repo under `config/`: `landmarks.yaml`, `games.yaml`, `teams.yaml` (teams plus team↔game assignments with validity window and exit message). Landmark pictures go under `config/images/`.
- A command-line script `sync-config`:
  1. validates the files (unique IDs, landmark references exist, Hint 2 only with Hint 1, at least one accepted answer, unique team names, valid time zone, etc.);
  2. upserts them into PostgreSQL and uploads the pictures to Blob storage;
  3. generates an access token for every assignment that doesn't have one yet, **writes it back into `teams.yaml`** (field `token` on the assignment), and prints each team's game link;
  4. can reissue a token (`--reissue <team> <game>`): replaces the token in `teams.yaml` and in the database, so the old link stops working at once.
- An optional `service:` block in `teams.yaml` (`team`, `name`, `tokens`) defines the service (test) team (R-25). `sync-config` issues one token per game in `games.yaml` and writes them under `service.tokens`; `--reissue <service-team> <game>` replaces one. The team is stored with `teams.is_service`, and its assignments get fixed sentinel validity windows because the window is ignored at runtime. Removing the block, or a game, deactivates those links through the normal path. `POST /api/play/{token}/reset` works only on service links (404 otherwise): it deletes the run with its tasks, attempts, photo rows, photo blobs and device rows, and raises `assignments.version_floor` so the next state version is higher than any a phone has already seen.
- `teams.yaml` is the record of all issued tokens. No separate token store is needed. Because it holds live game links, the repository must stay private, and the file must be committed after every `sync-config` run that issues or reissues tokens.
- The admin runs it after changing configuration; no redeploy is needed. At runtime the database is the only source of data, so a future CMS edits the database directly.
- A configuration change must not alter game runs that are already in progress. Each run keeps the task list it started with.

- Settings for the game request form (section 8), read from environment variables (see `backend/.env.example`):

  | Setting | Default | Meaning |
  |---|---|---|
  | `PUBLIC_SITE_ORIGIN` | unset | Origin of the website, no trailing slash (a trailing `/` and blanks are stripped). CORS for the API is enabled only when it is set. |
  | `REQUEST_MAX_TEAMS` | 10 | Teams per request |
  | `REQUEST_MAX_PENDING` | 50 | Pending requests accepted before the API answers 503 |
  | `REQUEST_MAX_PER_HOUR` | 20 | Requests accepted per rolling hour before the API answers 503 |
  | `REQUEST_RETENTION_DAYS` | 30 | Decided requests are deleted this many days after the decision. Must equal `legal.request_retention_days` on the website. |
  | `REQUEST_MIN_FILL_SECONDS` | 3 (0 or more) | Minimum time between issuing a challenge and submitting |
  | `REQUEST_CHALLENGE_MAX_NUMBER` | 50000 | Proof-of-work difficulty (the largest secret number) |
  | `REQUEST_CHALLENGE_SECRET` | a dev value | Key that signs challenges, at least 32 characters. In Azure it is a required `sensitive` Terraform variable. |
  | `DEFAULT_EXIT_MESSAGE` | empty | Exit message of assignments created by approving a request that has none of its own |

  `requestable` in `games.yaml` is optional. Omitted, it leaves the value set in the admin panel unchanged; new games start not requestable.

## 5. Photo storage

- Container `photos`, path `{GameName}/{TeamName}/{yyyy-MM-dd_HH-mm-ss}_{TaskNo}_{LandmarkName}.{ext}` (R-10), using the game's time zone. Folder and file names are built from the names at upload time.
- Container `albums`, path `{GameName}/{TeamName}/{yyyy-MM-dd}_memories-album.pdf` (issue #33): the team's memories album, rendered on the server (fpdf2 + Pillow, Onest bundled under `questtour/assets/fonts`) on the first request of `GET /api/play/{token}/album.pdf` or of the admin's *Generate*, and recorded in `team_albums`. The admin API lists, generates, downloads and deletes albums under `/api/admin/albums`; a deleted album answers 410 on the team's link. Photos are downscaled to 1600 px JPEG inside the PDF; the originals stay untouched.
- Upload goes through the backend, which checks the size (20 MB max) and the file type (JPEG, PNG, HEIC, WebP) and writes the blob. The original is never re-encoded.
- The container is private; no public access. Hosts get read/delete access through Azure RBAC (role *Storage Blob Data Contributor*).

## 6. Roles

| Role | Who | Access |
|---|---|---|
| Player | Anyone with a valid game link | Player API for that assignment only |
| Visitor | Anyone on the website | Public request API (section 8) only: list requestable games, submit a request |
| Host | Host staff (Entra ID users) | Read/delete photos in Blob storage |
| Admin | Operator (admin panel: e-mail + password, optionally Entra ID; Azure: Entra ID users) | Runs `sync-config`; uses the admin panel; manages Azure resources |

## 7. Deployment and operations

| Topic | Decision |
|---|---|
| Environments | `dev`: local, with PostgreSQL in Docker and the Azurite storage emulator. `prod`: Azure. No staging environment in v1. |
| Infrastructure as code | **Terraform** (azurerm provider) in `infra/`. State is kept remotely in a separate Azure Storage container. All resources in section 2 are defined there. |
| CI/CD | **GitHub Actions**. Pull requests run lint and tests (backend: pytest; frontend: unit tests); merging to `main` builds and deploys to prod. |
| Versioning | Releases are tags `vMAJOR.MINOR.PATCH` on `main`; pushing one publishes a GitHub Release and deploys that tag. Every build is named by `git describe` (the tag, `v1.2.0-3-g6dd4e31` past it, or a bare commit hash before the first tag). The package carries the name in a `VERSION` file, the SPA bakes it in at build time, the app footer shows it and `GET /api/health` reports it, so what runs can always be told apart from what was meant to run. |
| Environment variables | Use environment variables wherever a value differs between environments or must stay secret. Examples: database host/name, storage account name, public base URL for game links, Azure subscription/tenant IDs, Terraform variables (`TF_VAR_*`). **Backend and `sync-config`** read all settings from environment variables, with no hard-coded values; locally from a `.env` file (git-ignored, with a committed `.env.example`), in Azure from App Service app settings (secrets are `sensitive` Terraform variables, set from GitHub *secrets* by the Infra workflow and written into the app settings; there is no Key Vault). **CI/CD** reads them from GitHub Actions *variables* (non-secret) and *secrets* (secret); Azure login uses OIDC federated credentials, so no long-lived keys are stored. **Frontend** build-time values use Vite `VITE_*` variables, which must never hold secrets because they end up in the browser bundle. |
| Monitoring | None in v1, beyond the standard App Service logs. |
| Backups | PostgreSQL built-in backups with 7-day retention. Soft delete on the `photos` container with 14-day retention. |
| Budget | Azure budget alert at **€45/month**. |

## 8. Game requests

Issue #61. The website's form calls a public API; the admin decides in the admin panel (R-29). Code: `api/public.py`, `requests/service.py`, `requests/challenge.py`, `admin/router_requests.py`.

### 8.1 Data

- Table `game_requests` (migration `0009`): `id`, `host_id`, `game_id` (FK to `games`, `ON DELETE SET NULL`, nullable), `play_date`, `teams` (JSON list of `{name, key, participants|null, valid_from|null, valid_until|null, team_id|null}`; window bounds are UTC ISO strings, `null` means the play-date default; `team_id` is set on approval), `contact_name`, `contact_email`, `contact_phone`, `message`, `exit_message` (`null` means `DEFAULT_EXIT_MESSAGE`), `status` (`pending`, `approved`, `rejected`), `terms_accepted_at`, `terms_version`, `challenge` (**unique**), `decided_at`, `decided_by`, `created_at`, `updated_at`. Index on `(host_id, status)`.
- `created_at`, `terms_accepted_at` and `decided_at` always come from the injected clock; only `updated_at` uses the real clock (it backs the `seen_at` freshness check).
- `games.requestable` (boolean, default false) marks the games the public API offers.
- Deleting a game that has pending requests is refused with 409. For a game that is gone, the admin list shows no game name and approval answers 422 on `game_id`.

### 8.2 Public API

No authentication; always the configured host. Prefix `/api/public`.

- `GET /games` returns `[{key, name, intro}]` for requestable games, ordered by name. It never exposes tasks, landmarks or answers.
- `GET /requests/challenge` returns an ALTCHA-compatible proof-of-work challenge `{algorithm, challenge, maxnumber, salt, signature, min_fill_seconds, expires_in_seconds}` (`Cache-Control: no-store`). `salt` is `<16 random bytes in hex>?expires=<unix>`, `challenge` is `sha256hex(salt + N)` for a random `N` in `[0, maxnumber]`, `signature` is `HMAC-SHA256(REQUEST_CHALLENGE_SECRET, challenge)`, `algorithm` is `SHA-256`, and the lifetime is 600 seconds. The server stores nothing; the client brute-forces `N` and sends the object back with `number`. The two extra fields are ignored by ALTCHA clients; the form waits out `min_fill_seconds` measured from when it received the challenge, so it never compares its clock with the server's.
- `POST /requests` answers `201 {}` and never echoes data. Body fields: `game_key`, `play_date` (ISO), `teams` (1 to `REQUEST_MAX_TEAMS` of `name` 1-200 characters, `key` matching `^[a-z0-9][a-z0-9-]*$` up to 100, `participants` 1-500 or null), `contact_name` (1-200), `contact_email`, `contact_phone` (`^\+?[0-9 ()/-]{6,32}$`; at least one of the two), `message` (up to 2000), `terms_accepted` (must be `true`), `terms_version`, `website` (honeypot), `altcha` (the solved challenge). Strings are stripped; an empty optional one counts as not given; unknown fields are rejected. Error bodies are `{"errors": [{field, message}]}`.

  The checks run in this order, which is part of the contract:

  | # | Check | Result |
  |---|---|---|
  | 1 | Body over 16 KB (from `Content-Length` and from the bytes actually read) | `413 {"detail": "too_large"}` |
  | 2 | Schema, unique team names (case-insensitive) and keys within the request | 422 |
  | 3 | Honeypot `website` not empty | silent `201`, nothing stored, log `honeypot` |
  | 4 | Challenge: signature, solution (wrong hash or number above the cap), expiry, reuse | 422 `altcha` (one message for all), log `challenge_signature`, `challenge_solution`, `challenge_expired` or `challenge_reused` |
  | 5 | Fill time: server time now minus issue time is below `REQUEST_MIN_FILL_SECONDS` | silent `201`, nothing stored, log `too_fast` |
  | 6 | Purge of decided requests past retention | |
  | 7 | Pending requests at or over `REQUEST_MAX_PENDING` | `503 {"detail": "not_accepting"}`, log `pending_cap` |
  | 8 | Requests created in the last hour at or over `REQUEST_MAX_PER_HOUR` | `503 {"detail": "not_accepting"}`, log `hourly_cap` |
  | 9 | Unknown or non-requestable game (one message for both, so games cannot be enumerated), or play date outside today to today + 365 days in the game's time zone | 422 `game_key` or `play_date` |
  | 10 | A pending request with the same game, play date and e-mail (lower-cased), or, without an e-mail, the same phone (a leading `+` kept, then digits only) | `409` on `contact_email` or `contact_phone`, log `duplicate` |
  | 11 | A team key, or a team name compared case-insensitively, that already exists for the host | 422 on `teams.<i>.key` or `teams.<i>.name` |
  | 12 | Insert as `pending` (one commit) | `201`, log `stored`; a unique violation on the challenge gives 422 `altcha`, log `challenge_reused` |

- **Single use.** A challenge is consumed when it is stored with a request (unique `game_requests.challenge`), so a restart or a second worker cannot reopen it. Responses 413, 422, 409 and 503 and the silent drops do not consume it.
- **Minimum fill time.** Measured on the server as now minus the issue time (`expires` minus the lifetime). A client that waits `min_fill_seconds` after receiving the challenge is never dropped.

### 8.3 Admin API

All routes under `/api/admin/requests` require an admin session and the admin's host; another host's id answers 404.

- `GET ?status=pending|approved|rejected|all` (default `pending`, anything else 422) runs the purge first and returns `[{id, created_at, contact_name, game_id, game_name, play_date, team_count, status}]`, newest first. The number of pending requests drives the navigation badge and the Dashboard card.
- `GET /{id}` returns the full request, including consent time and version, with each team's window and the exit message resolved: the play date from 00:00 to 23:59:59 in the game's time zone, and `DEFAULT_EXIT_MESSAGE`.
- `PUT /{id}` with `{game_id, exit_message, teams, seen_at}` edits a pending request (any game of the host, requestable or not). Team fields are validated like admin-panel teams; windows are parsed in the game's time zone and must have start before end. Errors are 422 on `teams.<i>.*`.
- `POST /{id}/approve` with `{seen_at}` runs in one transaction: it checks the game and the team clashes (422, nothing created), flips the status from `pending` only if it still is (otherwise 409), creates each team with its assignment (resolved window and exit message) and a token, and stores `team_id` in the request. It answers with the same token reveals as the team assignment API (`assignment_id`, `token`, `url`). A race on a team key or name rolls everything back and leaves the request pending.
- `POST /{id}/reject` with `{seen_at}` flips `pending` to `rejected` and creates nothing.
- A decided request cannot be changed: edit, approve and reject answer `409 {entity: "GameRequest", current: <detail>}`, and the admin UI reloads into read-only mode.
- **Retention.** There is no scheduler. The purge deletes approved and rejected requests whose `decided_at` is older than `REQUEST_RETENTION_DAYS`; it runs on every `POST /api/public/requests` and every `GET /api/admin/requests`. Pending requests are never purged.

### 8.4 Protection and logging

- Layers: proof of work, honeypot, minimum fill time, the 16 KB body limit, the pending and hourly caps, and the duplicate check. The caps are soft ceilings: concurrent submissions can exceed them by a few rows (one worker in production).
- The log (`questtour.requests`) holds reason codes only (`honeypot`, `challenge_*`, `too_fast`, `pending_cap`, `hourly_cap`, `duplicate`, `stored`). It never contains an e-mail address, phone number, name, message or IP address.
- No e-mail is sent in v1.

### 8.5 CORS

`CORSMiddleware` is added only when `PUBLIC_SITE_ORIGIN` is set. It allows that single origin, methods `GET` and `POST`, header `Content-Type`, and no credentials, so cross-origin scripts cannot use the admin session cookie. It is the outermost middleware, so preflights and error responses carry the headers. When the setting is empty the form on the website fails; set it through Terraform before shipping the website change.
