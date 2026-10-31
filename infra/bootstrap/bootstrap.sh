#!/usr/bin/env bash
# One-off bootstrap for what Terraform itself depends on (clarify: az CLI script + README steps):
# state storage, the app resource group, the two GitHub OIDC identities and their roles, the repo's
# OIDC subject template and the GitHub Actions variables. Works on every GitHub plan: no GitHub
# environments are used (infra/README.md, "GitHub plan").
#
# Run once by a subscription Owner who is also an admin of the GitHub repo, after `az login` and
# `gh auth login`. Safe to re-run: everything is get-or-create-or-update.
#   GITHUB_REPO=owner/repo STATE_ACCOUNT=<unique> APP_NAME=<app_name> BUDGET_EMAIL=<you@example.com> \
#     [ADMIN_IP=<your public IPv4>] [ADMIN_BOOTSTRAP_EMAIL=<first admin email>] bash infra/bootstrap/bootstrap.sh
set -euo pipefail

: "${GITHUB_REPO:?set GITHUB_REPO=owner/repo}"
: "${STATE_ACCOUNT:?set STATE_ACCOUNT (3-24 lowercase letters/digits, globally unique)}"
: "${APP_NAME:?set APP_NAME (same value as the Terraform app_name variable)}"
: "${BUDGET_EMAIL:?set BUDGET_EMAIL (receives the budget alerts)}"
LOCATION="${LOCATION:-westeurope}"
STATE_RG="${STATE_RG:-rg-questtour-tfstate}"
STATE_CONTAINER="${STATE_CONTAINER:-tfstate}"
APP_RG="${APP_RG:-rg-${APP_NAME}}"
# workflow: each identity trusts exactly one workflow file on main (default; needs the repo OIDC
#           subject template below). default: both trust any workflow run on main (fallback).
OIDC_SUBJECT_TEMPLATE="${OIDC_SUBJECT_TEMPLATE:-workflow}"
# auto | immutable | legacy. GitHub uses repo:owner@ID/repo@ID for repos created after 2026-07-15.
OIDC_SUBJECT_FORMAT="${OIDC_SUBJECT_FORMAT:-auto}"

for tool in az gh; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done
gh auth status >/dev/null || { echo "run 'gh auth login' first" >&2; exit 1; }

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
az account set --subscription "$SUBSCRIPTION_ID"
TENANT_ID="$(az account show --query tenantId -o tsv)"

has_role() { # principalObjectId role scope
  [ "$(az role assignment list --assignee "$1" --role "$2" --scope "$3" --query 'length(@)' -o tsv)" != "0" ]
}
assign() { # principalObjectId principalType role scope
  has_role "$1" "$3" "$4" ||
    az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" \
      --role "$3" --scope "$4" -o none
}
ensure_app() { # displayName -> appId
  local id
  id="$(az ad app list --display-name "$1" --query '[0].appId' -o tsv)"
  [ -n "$id" ] || id="$(az ad app create --display-name "$1" --query appId -o tsv)"
  az ad sp show --id "$id" -o none 2>/dev/null || az ad sp create --id "$id" -o none
  echo "$id"
}
ensure_federated() { # appId credentialName subject
  local current params
  params="{\"name\":\"$2\",\"issuer\":\"https://token.actions.githubusercontent.com\",\"subject\":\"$3\",\"audiences\":[\"api://AzureADTokenExchange\"]}"
  current="$(az ad app federated-credential list --id "$1" --query "[?name=='$2'].subject | [0]" -o tsv)"
  if [ -z "$current" ]; then
    az ad app federated-credential create --id "$1" --parameters "$params" -o none
  elif [ "$current" != "$3" ]; then
    az ad app federated-credential update --id "$1" --federated-credential-id "$2" \
      --parameters "$params" -o none
  fi
}
set_var() { # name value
  gh variable set "$1" --repo "$GITHUB_REPO" --body "$2"
}

echo "Registering resource providers (Terraform runs with resource_provider_registrations = none)..."
for ns in Microsoft.Web Microsoft.DBforPostgreSQL Microsoft.Storage Microsoft.Consumption; do
  az provider register --namespace "$ns" -o none
done

echo "Terraform state storage..."
az group create -n "$STATE_RG" -l "$LOCATION" -o none
if ! az storage account show -n "$STATE_ACCOUNT" -g "$STATE_RG" -o none 2>/dev/null; then
  az storage account create -n "$STATE_ACCOUNT" -g "$STATE_RG" -l "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
    --allow-blob-public-access false --allow-shared-key-access false -o none
fi
az storage account blob-service-properties update -n "$STATE_ACCOUNT" -g "$STATE_RG" \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 30 -o none
# Management-plane create: works with shared keys disabled and needs no data-plane role yet.
az storage container-rm create --storage-account "$STATE_ACCOUNT" -g "$STATE_RG" \
  --name "$STATE_CONTAINER" -o none
STATE_ACCOUNT_ID="$(az storage account show -n "$STATE_ACCOUNT" -g "$STATE_RG" --query id -o tsv)"
ME_ID="$(az ad signed-in-user show --query id -o tsv)"
ME_UPN="$(az ad signed-in-user show --query userPrincipalName -o tsv)"
assign "$ME_ID" User "Storage Blob Data Contributor" "$STATE_ACCOUNT_ID" # local terraform runs

echo "App resource group..."
az group create -n "$APP_RG" -l "$LOCATION" -o none
APP_RG_ID="$(az group show -n "$APP_RG" --query id -o tsv)"

echo "GitHub OIDC subjects..."
IFS=$'\t' read -r OWNER OWNER_ID REPO REPO_ID CREATED_AT < <(
  gh api "repos/$GITHUB_REPO" --jq '[.owner.login, .owner.id, .name, .id, .created_at] | @tsv'
)
if [ "$OIDC_SUBJECT_FORMAT" = auto ]; then
  if [[ "$CREATED_AT" > "2026-07-15" ]]; then OIDC_SUBJECT_FORMAT=immutable; else OIDC_SUBJECT_FORMAT=legacy; fi
fi
case "$OIDC_SUBJECT_FORMAT" in
  immutable) REPO_SEGMENT="${OWNER}@${OWNER_ID}/${REPO}@${REPO_ID}" ;;
  legacy) REPO_SEGMENT="${OWNER}/${REPO}" ;;
  *) echo "OIDC_SUBJECT_FORMAT must be auto, immutable or legacy" >&2; exit 1 ;;
esac
MAIN="repo:${REPO_SEGMENT}:ref:refs/heads/main"
WORKFLOWS="${OWNER}/${REPO}/.github/workflows"
case "$OIDC_SUBJECT_TEMPLATE" in
  workflow)
    INFRA_SUBJECT="${INFRA_SUBJECT:-${MAIN}:job_workflow_ref:${WORKFLOWS}/infra.yml@refs/heads/main}"
    DEPLOY_SUBJECT="${DEPLOY_SUBJECT:-${MAIN}:job_workflow_ref:${WORKFLOWS}/deploy.yml@refs/heads/main}"
    TEMPLATE='{"use_default":false,"include_claim_keys":["repo","context","job_workflow_ref"]}'
    ;;
  default)
    INFRA_SUBJECT="${INFRA_SUBJECT:-$MAIN}"
    DEPLOY_SUBJECT="${DEPLOY_SUBJECT:-$MAIN}"
    TEMPLATE='{"use_default":true}'
    ;;
  *) echo "OIDC_SUBJECT_TEMPLATE must be workflow or default" >&2; exit 1 ;;
esac

echo "GitHub OIDC identities..."
INFRA_APP_ID="$(ensure_app questtour-gh-infra)"
DEPLOY_APP_ID="$(ensure_app questtour-gh-deploy)"
INFRA_SP="$(az ad sp show --id "$INFRA_APP_ID" --query id -o tsv)"
DEPLOY_SP="$(az ad sp show --id "$DEPLOY_APP_ID" --query id -o tsv)"
ensure_federated "$INFRA_APP_ID" github-main-infra "$INFRA_SUBJECT"
ensure_federated "$DEPLOY_APP_ID" github-main-deploy "$DEPLOY_SUBJECT"

assign "$INFRA_SP" ServicePrincipal "Contributor" "$APP_RG_ID"
assign "$INFRA_SP" ServicePrincipal "Role Based Access Control Administrator" "$APP_RG_ID"
assign "$INFRA_SP" ServicePrincipal "Storage Blob Data Contributor" "$STATE_ACCOUNT_ID"
# The deploy identity gets Website Contributor on the web app from Terraform (rbac.tf).

# GitHub's advice: create the matching federated credential first, then switch the token format.
echo "Repository OIDC subject template ($OIDC_SUBJECT_TEMPLATE)..."
gh api --method PUT "repos/$GITHUB_REPO/actions/oidc/customization/sub" --input - <<<"$TEMPLATE" >/dev/null

echo "GitHub Actions repository variables (no secrets: Azure login is OIDC)..."
set_var AZURE_TENANT_ID "$TENANT_ID"
set_var AZURE_SUBSCRIPTION_ID "$SUBSCRIPTION_ID"
set_var AZURE_RESOURCE_GROUP "$APP_RG"
set_var AZURE_INFRA_CLIENT_ID "$INFRA_APP_ID"
set_var AZURE_DEPLOY_CLIENT_ID "$DEPLOY_APP_ID"
set_var AZURE_WEBAPP_NAME "app-$APP_NAME"
set_var TFSTATE_RESOURCE_GROUP "$STATE_RG"
set_var TFSTATE_STORAGE_ACCOUNT "$STATE_ACCOUNT"
set_var TFSTATE_CONTAINER "$STATE_CONTAINER"
set_var TF_APP_NAME "$APP_NAME"
set_var TF_DEPLOY_PRINCIPAL_OBJECT_ID "$DEPLOY_SP"
set_var TF_ADMIN_PRINCIPAL_OBJECT_ID "${ADMIN_OBJECT_ID:-$ME_ID}"
set_var TF_ADMIN_PRINCIPAL_NAME "${ADMIN_NAME:-$ME_UPN}"
set_var TF_ADMIN_PRINCIPAL_TYPE "${ADMIN_TYPE:-User}"
set_var TF_BUDGET_CONTACT_EMAILS "[\"$BUDGET_EMAIL\"]"
if [ -n "${ADMIN_IP:-}" ]; then set_var TF_ADMIN_IP_ADDRESSES "{\"admin\":\"$ADMIN_IP\"}"; fi
if [ -n "${ADMIN_BOOTSTRAP_EMAIL:-}" ]; then set_var ADMIN_BOOTSTRAP_EMAIL "$ADMIN_BOOTSTRAP_EMAIL"; fi

cat <<EOF

Bootstrap done.
  infra identity  questtour-gh-infra   trusts  $INFRA_SUBJECT
  deploy identity questtour-gh-deploy  trusts  $DEPLOY_SUBJECT
Next (infra/README.md, first-time setup): on main, Actions -> "Infrastructure (Terraform)" -> Run
workflow (plan), then apply; then db-setup; then run "Deploy" once by hand; then
  gh variable set DEPLOY_ENABLED --repo $GITHUB_REPO --body true
to let merges to main deploy automatically.
If an Azure login fails with AADSTS700213, compare the "OIDC subject" line in that job's log with the
subjects above and re-run with INFRA_SUBJECT=... / DEPLOY_SUBJECT=... (or OIDC_SUBJECT_FORMAT=...).
Admin sign-in is email + password: add secret ADMIN_BOOTSTRAP_PASSWORD (>=12 chars) under
Settings -> Secrets, and set variable ADMIN_BOOTSTRAP_EMAIL if not passed here.
Optional: TF_HOST_PRINCIPAL_OBJECT_IDS (JSON list) for host staff photo access.
EOF
