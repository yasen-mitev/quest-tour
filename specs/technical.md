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
| Secrets | App Service settings or Key Vault references | |

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
- **Admin sign-in.** The admin panel (`/admin`, API under `/api/admin`) signs in with e-mail and password by default. `ADMIN_AUTH_PROVIDER` selects one of three modes: `dev` (local magic link for `ADMIN_DEV_EMAILS`; the Python default, rejected in production), `password` (the Terraform default) and `entra` (password **and** Microsoft Entra sign-in, for upgraded legacy deployments). Admins live in the `admin_users` table (e-mail, argon2id password hash); runtime switches live in the `app_settings` table, currently the Entra on/off toggle. Entra can be enabled later from the Settings screen if the `ADMIN_ENTRA_*` settings are configured; they are required only in `entra` mode. The first admin is seeded from `ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` (12 characters or more) on first start only. After that the database owns the password, and the recovery CLI is `admin-password --email <e-mail>`.
  - `POST /api/admin/auth/password` signs in with e-mail and password (throttled in memory, per instance). `GET /api/admin/auth/provider` tells the login screen which sign-ins to offer; `login`, `callback` (Entra), `magic/request` and `magic/verify` (dev) and `logout` complete the set.
  - `/api/admin/account/*` serves the signed-in admin: `auth-settings` (read the session provider and the Entra toggle, change the toggle), `password` (change own password), and `admins` (list, add, delete, and set another admin's password).
  - The admin SPA's **Settings** screen (`/admin/settings`) is the UI for those endpoints. A password change does not invalidate other sessions.

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

## 5. Photo storage

- Container `photos`, path `{GameName}/{TeamName}/{yyyy-MM-dd_HH-mm-ss}_{TaskNo}_{LandmarkName}.{ext}` (R-10), using the game's time zone. Folder and file names are built from the names at upload time.
- Container `albums`, path `{GameName}/{TeamName}/{yyyy-MM-dd}_memories-album.pdf` (issue #33): the team's memories album, rendered on the server (fpdf2 + Pillow, Onest bundled under `questtour/assets/fonts`) on the first request of `GET /api/play/{token}/album.pdf` or of the admin's *Generate*, and recorded in `team_albums`. The admin API lists, generates, downloads and deletes albums under `/api/admin/albums`; a deleted album answers 410 on the team's link. Photos are downscaled to 1600 px JPEG inside the PDF; the originals stay untouched.
- Upload goes through the backend, which checks the size (20 MB max) and the file type (JPEG, PNG, HEIC, WebP) and writes the blob. The original is never re-encoded.
- The container is private; no public access. Hosts get read/delete access through Azure RBAC (role *Storage Blob Data Contributor*).

## 6. Roles

| Role | Who | Access |
|---|---|---|
| Player | Anyone with a valid game link | Player API for that assignment only |
| Host | Host staff (Entra ID users) | Read/delete photos in Blob storage |
| Admin | Operator (admin panel: e-mail + password, optionally Entra ID; Azure: Entra ID users) | Runs `sync-config`; uses the admin panel; manages Azure resources |

## 7. Deployment and operations

| Topic | Decision |
|---|---|
| Environments | `dev`: local, with PostgreSQL in Docker and the Azurite storage emulator. `prod`: Azure. No staging environment in v1. |
| Infrastructure as code | **Terraform** (azurerm provider) in `infra/`. State is kept remotely in a separate Azure Storage container. All resources in section 2 are defined there. |
| CI/CD | **GitHub Actions**. Pull requests run lint and tests (backend: pytest; frontend: unit tests); merging to `main` builds and deploys to prod. |
| Versioning | Releases are tags `vMAJOR.MINOR.PATCH` on `main`; pushing one publishes a GitHub Release and deploys that tag. Every build is named by `git describe` (the tag, `v1.2.0-3-g6dd4e31` past it, or a bare commit hash before the first tag). The package carries the name in a `VERSION` file, the SPA bakes it in at build time, the app footer shows it and `GET /api/health` reports it, so what runs can always be told apart from what was meant to run. |
| Environment variables | Use environment variables wherever a value differs between environments or must stay secret. Examples: database host/name, storage account name, public base URL for game links, Azure subscription/tenant IDs, Terraform variables (`TF_VAR_*`). **Backend and `sync-config`** read all settings from environment variables, with no hard-coded values; locally from a `.env` file (git-ignored, with a committed `.env.example`), in Azure from App Service app settings (secrets as Key Vault references). **CI/CD** reads them from GitHub Actions *variables* (non-secret) and *secrets* (secret); Azure login uses OIDC federated credentials, so no long-lived keys are stored. **Frontend** build-time values use Vite `VITE_*` variables, which must never hold secrets because they end up in the browser bundle. |
| Monitoring | None in v1, beyond the standard App Service logs. |
| Backups | PostgreSQL built-in backups with 7-day retention. Soft delete on the `photos` container with 14-day retention. |
| Budget | Azure budget alert at **€45/month**. |
