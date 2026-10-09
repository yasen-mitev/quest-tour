data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "app" {
  name = var.resource_group_name
}

locals {
  location       = data.azurerm_resource_group.app.location
  web_app_name   = "app-${var.app_name}"
  plan_name      = "asp-${var.app_name}"
  pg_server_name = "psql-${var.app_name}"
  storage_name   = "st${replace(var.app_name, "-", "")}"

  pg_fqdn         = "${local.pg_server_name}.postgres.database.azure.com"
  storage_url     = "https://${local.storage_name}.blob.core.windows.net"
  public_base_url = "https://${local.web_app_name}.azurewebsites.net" # clarify: default hostname only

  tags = { app = "quest-tour", env = "prod", managed_by = "terraform" }

  # Every value questtour.settings reads in prod (technical §7: app settings, no secrets needed).
  app_settings = {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    DATABASE_URL                   = "postgresql+psycopg://${local.web_app_name}@${local.pg_fqdn}:5432/${var.db_name}?sslmode=require"
    DATABASE_AUTH                  = "azure_ad"
    DATABASE_OWNER_ROLE            = var.db_owner_role
    HOST_ID                        = "default"
    PUBLIC_BASE_URL                = local.public_base_url
    STORAGE_BACKEND                = "azure"
    AZURE_STORAGE_ACCOUNT_URL      = local.storage_url
    PHOTOS_CONTAINER               = azurerm_storage_container.photos.name
    IMAGES_CONTAINER               = azurerm_storage_container.images.name
    ALBUMS_CONTAINER               = azurerm_storage_container.albums.name
    STATIC_DIR                     = "static"
    # Admin panel auth (Microsoft Entra). Redirect URI must match the Entra app registration.
    ADMIN_AUTH_PROVIDER           = "entra"
    ADMIN_SESSION_SECRET          = var.admin_session_secret
    ADMIN_SESSION_SECURE          = "true"
    ADMIN_SESSION_MAX_AGE_MINUTES = "720"
    ADMIN_ENTRA_TENANT_ID         = var.admin_entra_tenant_id
    ADMIN_ENTRA_CLIENT_ID         = var.admin_entra_client_id
    ADMIN_ENTRA_CLIENT_SECRET     = var.admin_entra_client_secret
    ADMIN_ENTRA_REDIRECT_URI      = "${local.public_base_url}/api/admin/auth/callback"
    ADMIN_ENTRA_GROUP_OBJECT_ID   = var.admin_entra_group_object_id
  }
}
