# Infrastructure and deployment (Azure)

Quest City Tour runs on one Azure App Service (Linux, Python 3.12) with PostgreSQL Flexible Server and
Blob storage. Terraform in `infra/` describes everything; GitHub Actions in `.github/workflows/` build,
test and deploy it. This file is the runbook.

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | pull request; reused by `deploy.yml` | backend ruff + pytest (SQLite and PostgreSQL), Alembic on PostgreSQL, frontend typecheck + vitest, static checks of the DevOps files, build and smoke test of the deploy package |
| `deploy.yml` | push to `main` (once `DEPLOY_ENABLED=true`), or manual | re-runs CI, zip-deploys to App Service through GitHub OIDC, then checks `/api/health` |
| `infra.yml` | manual only | Terraform `plan`, or `plan` + `apply` after typing `APPLY` |

## 1. What gets created

| Resource | Name | Made by |
|---|---|---|
| Resource group | `rg-<n>` | `bootstrap.sh` |
| App Service plan (B1, Linux) | `asp-<n>` | Terraform |
| Web app | `app-<n>` | Terraform |
| PostgreSQL Flexible Server 16 (B1ms, 32 GB) | `psql-<n>` | Terraform |
| Storage account (`photos`, `images` containers) | `st<n without hyphens>` | Terraform |
| Monthly budget with alerts at 80 % actual and 100 % forecast | `budget-<n>-monthly` | Terraform |
| Terraform state storage and the two GitHub OIDC identities | see `bootstrap.sh` | `bootstrap.sh` |

`<n>` is the Terraform `app_name` variable (3-20 characters, `[a-z0-9-]`). The database `questtour` and
its roles are created by `db-setup`, not by Terraform.

Estimated cost is about €30 per month: App Service B1 ≈ €12, PostgreSQL B1ms ≈ €13, 32 GB storage ≈ €4,
blobs and backups ≈ €1-2. The €45 budget alert is in your billing currency.

## 2. GitHub plan (prerequisites)

This works on **every GitHub plan, including Free with a private repository**. It uses only
repository-level Actions variables and OIDC: no environments, no environment variables or secrets, and
no required reviewers. GitHub's docs say why:

- "Users with GitHub Free plans can only configure environments for public repositories", and
  "Organizations with GitHub Team and users with GitHub Pro can configure environments for private
  repositories."
- "If you are on a GitHub Free, GitHub Pro, or GitHub Team plan, required reviewers are only available
  for public repositories."

**What replaces required reviewers** for *Infrastructure (Terraform)*:

- only collaborators with write access can run it;
- it refuses any ref but `main`;
- `apply` requires typing `APPLY` in the `confirm` input;
- the procedure is: run `plan`, read the job summary, then run `apply`.

**Identity separation.** The repository's OIDC subject template includes `job_workflow_ref`, so the
infra identity only works from `infra.yml` on `main`, and the deploy identity only from `deploy.yml` on
`main`. Pull-request runs match neither. Branch protection for `main` is recommended wherever your plan
offers it, because "code on `main`" is the trust boundary.

**Optional hardening** (GitHub Enterprise, or a public repository): add an environment with required
reviewers to the `terraform` job. The OIDC `context` then changes, so re-run the bootstrap with
`INFRA_SUBJECT='repo:<seg>:environment:<env>:job_workflow_ref:<owner>/<repo>/.github/workflows/infra.yml@refs/heads/main'`.

## 3. First-time setup

Do these in this order. The order is forced: *Infrastructure (Terraform)* can only be dispatched from
`main`.

1. **Merge the PR that adds these workflows.** CI runs on `main`. *Deploy* shows its `deploy` job as
   *skipped*, because `DEPLOY_ENABLED` is not set yet. That is expected, not a failure.
2. Prerequisites: `az login` as a subscription Owner, and `gh auth login` as a repository admin.
3. Run the bootstrap (it may also run before step 1):

   ```bash
   GITHUB_REPO=yasen-mitev/quest-tour STATE_ACCOUNT=<unique> APP_NAME=<name> BUDGET_EMAIL=<you> \
     ADMIN_IP=<your IPv4> bash infra/bootstrap/bootstrap.sh
   ```

   - It sets every repository variable except `DEPLOY_ENABLED`. Check them under Settings → Secrets and
     variables → Actions → Variables.
   - Make sure your IP is in `TF_ADMIN_IP_ADDRESSES` (the `ADMIN_IP` above) before the apply, because
     `db-setup` and `sync-config` need it.
4. Actions → *Infrastructure (Terraform)* → Run workflow on `main` → `plan`. Read the job summary, then
   run it again with `apply` and `confirm = APPLY`.
5. From `backend/`, after `az login`:

   ```bash
   uv run db-setup --host psql-<name>.postgres.database.azure.com --admin-role '<admin UPN>' --app-role app-<name>
   ```

   - The `db_setup_command` Terraform output prints this exact command.
   - Run it with `--dry-run` first.
   - On the Windows build machine, use WSL: psycopg is blocked there.
6. Actions → *Deploy* → Run workflow on `main` with `ref` empty. It waits for `/api/health`.
7. Enable automatic deploys on merge:
   `gh variable set DEPLOY_ENABLED --repo yasen-mitev/quest-tour --body true`.
8. Run `sync-config` against prod:
   - load the `admin_sync_config_env` output as real environment variables, which beat `backend/.env`.
     Copy the lines from the Infra apply's job summary, or run, from an `infra/` initialised with the
     same `-backend-config` values:
     `set -a; eval "$(terraform output -raw admin_sync_config_env)"; set +a`;
   - run `uv run sync-config`;
   - commit `teams.yaml`. That push does not trigger a deploy.

## 3.1 Admin panel (Entra sign-in)

The admin panel at `/admin` signs in through Microsoft Entra. Prerequisites outside this repo:

- An **Entra app registration** (Web platform) with redirect URI
  `https://app-<name>.azurewebsites.net/api/admin/auth/callback` (derive it from
  `terraform output web_app_url`) and delegated Graph permission `User.Read` (admin consent granted).
- An **Entra group** whose members may use the panel; its Object ID becomes
  `ADMIN_ENTRA_GROUP_OBJECT_ID`.

Then wire the values into GitHub (see §4) and run Infra `plan` → `apply`. The apply sets
`ADMIN_AUTH_PROVIDER=entra` and the related app settings, and App Service restarts with them.

## 3.2 Admin panel (developer sign-in, optional)

For a local admin panel, set `ADMIN_AUTH_PROVIDER=dev` and `ADMIN_DEV_EMAILS` in `backend/.env`
(see `backend/.env.example`). Never set `ADMIN_AUTH_PROVIDER=dev` on App Service: the prod plan
pins `entra`.

## 4. GitHub variables

All are repository-scope Actions variables. Azure login is OIDC, so there are **no Azure
secrets**; the only GitHub **secrets** are the admin panel's Entra client secret and session
secret (see §3.1). `bootstrap.sh` sets all of them except the optional
`TF_HOST_PRINCIPAL_OBJECT_IDS`, `DEPLOY_ENABLED` and the admin panel entries.

| Variable | Meaning |
|---|---|
| `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Entra tenant and Azure subscription |
| `AZURE_RESOURCE_GROUP` | the app resource group |
| `AZURE_INFRA_CLIENT_ID`, `AZURE_DEPLOY_CLIENT_ID` | client IDs of `questtour-gh-infra` and `questtour-gh-deploy` |
| `AZURE_WEBAPP_NAME` | `app-<n>` |
| `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `TFSTATE_CONTAINER` | Terraform remote state |
| `TF_APP_NAME` | the `app_name` Terraform variable |
| `TF_DEPLOY_PRINCIPAL_OBJECT_ID` | object ID of the deploy identity |
| `TF_ADMIN_PRINCIPAL_OBJECT_ID`, `TF_ADMIN_PRINCIPAL_NAME`, `TF_ADMIN_PRINCIPAL_TYPE` | the admin: PostgreSQL Entra admin and blob access |
| `TF_ADMIN_IP_ADDRESSES` | JSON map name → IPv4 for the PostgreSQL firewall |
| `TF_HOST_PRINCIPAL_OBJECT_IDS` | optional JSON list of host staff object IDs (photo access) |
| `TF_BUDGET_CONTACT_EMAILS` | JSON list of budget alert e-mail addresses |
| `DEPLOY_ENABLED` | set by hand in first-time setup step 7. `true` lets pushes to `main` deploy; anything else pauses auto-deploys, while manual *Deploy* runs still work |
| `ADMIN_ENTRA_TENANT_ID`, `ADMIN_ENTRA_CLIENT_ID`, `ADMIN_ENTRA_GROUP_OBJECT_ID` | admin panel: Entra tenant, app registration client ID, and the Object ID of the admin group (§3.1) |
| `ADMIN_ENTRA_CLIENT_SECRET` | **secret**: client secret of the admin panel Entra app (§3.1) |
| `ADMIN_SESSION_SECRET` | **secret**: ≥32-byte random string signing admin session cookies. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

## 5. Budget start date

- The budget starts on the first day of the month of the **first** apply, because Azure refuses past
  months.
- After that, `ignore_changes` keeps it.
- To recreate the budget later, taint it or remove it from state. The new apply then uses the current
  month again.
- Local runs can override it with `TF_VAR_budget_start_date=YYYY-MM-01T00:00:00Z`.

## 6. Day-2 operations

- Add an admin IP or a host: edit the variable, then run Infra `plan` → `apply`.
- Logs: `az webapp log tail -g <rg> -n app-<name>`.
- **Roll back**: Actions → *Deploy* → Run workflow **on `main`** with `ref=<older SHA>`. Never roll back
  across an Alembic migration, because the old code can't find the new head. Use a revert commit
  instead. Only commits that already contain the deploy scripts can be deployed.
- An additional admin: `db-setup --member '<upn>'`, run by the original admin.
- Local `terraform plan`: the same `-backend-config` values, plus `ARM_SUBSCRIPTION_ID` and `az login`.
- Re-run `bootstrap.sh` safely (it is idempotent) to rotate subjects or to fix variables.
- Pause auto-deploys, e.g. on an event day: `gh variable set DEPLOY_ENABLED --body false`.
- The post-deploy health check cannot tell old code from new. During a redeploy the old instance may
  still answer for a short time, so a green check is conclusive on the first deploy and only indicative
  later. If a redeploy looks suspicious, read the deployment log (Portal → Deployment Center, or
  `az webapp log deployment show -g <rg> -n app-<name>`) and `az webapp log tail`.

## 7. Security notes

- PostgreSQL is Entra-only: no passwords. The `0.0.0.0` firewall rule means "allow Azure services"; App
  Service's outbound addresses are shared and change. Every other address needs its own admin rule.
- Storage has no shared keys, private containers and RBAC-only access. The network default is *Allow*:
  storage IP rules don't apply to same-region App Service traffic, and hosts browse photos from
  anywhere.
- `prevent_destroy` is set on PostgreSQL and storage.
- The OIDC subject template is what keeps the infra and deploy identities apart. Without it, any job on
  `main`, including a third-party action, could log in as either.
- The infra identity has Contributor and *Role Based Access Control Administrator* on the app resource
  group only, plus *Storage Blob Data Contributor* on the state account. Its RBAC Administrator role is
  unconstrained inside that group, so a compromised `infra.yml` on `main` could grant itself *Owner*
  there. Optional hardening: re-create that assignment with an ABAC condition limiting
  `roleAssignments/write` and `roleAssignments/delete` to the role definition IDs of *Storage Blob Data
  Contributor*, *Reader* and *Website Contributor*. It is not in `bootstrap.sh`, because the condition
  string can't be verified without `az`.
- `backend/config/` holds live game tokens and is never part of the deploy package.

## 8. Troubleshooting

- **AADSTS700213 "No matching federated identity record"**: copy the `OIDC subject:` line from the
  failed job, then re-run the bootstrap with `INFRA_SUBJECT=…` / `DEPLOY_SUBJECT=…`, or with
  `OIDC_SUBJECT_FORMAT=legacy|immutable`.
- **Subject template PUT refused**: re-run with `OIDC_SUBJECT_TEMPLATE=default`. That gives weaker
  separation: both identities trust any workflow on `main`.
- **psycopg DLL blocked** by Windows Application Control: run `db-setup` / `sync-config` from WSL or
  another machine.
- **`pgaadauth_create_principal` can't find the identity**: check that the web app exists and that
  `--app-role` equals the web app name.
- **Deploy fails with 401/403**: check the deploy identity's *Website Contributor* assignment (Terraform
  `rbac.tf`) and the federated subject. If both are right, switch that assignment's
  `role_definition_name` to `Contributor`, still scoped to the web app, and update the `prod_shape`
  assert in `infra/tests/plan.tftest.hcl` to match.
- **First apply fails with a storage 403 on a data-plane call**: grant the infra identity *Storage Blob
  Data Contributor* on the app storage account (`st<n>`) and re-apply.
- **UPN longer than 63 characters**: PostgreSQL identifiers are at most 63 bytes. Use an Entra group as
  the admin (`ADMIN_TYPE=Group`).
- **`GRANT` fails in `db-setup` on a re-run**: `questtour_owner` was created by a different admin, who
  alone holds ADMIN OPTION. Have that admin run `db-setup --member '<upn>'`.
- **Budget create refused** ("subscription offer not supported"): some offer types (some sponsored or
  credit-based ones) don't support Azure budgets. Set up a cost alert in the Portal instead, and remove
  the budget from the plan with `terraform state rm`, or comment `budget.tf`'s resource out.
- **Deploy job "skipped" on a push**: `DEPLOY_ENABLED` is not `true` (first-time setup step 7).
