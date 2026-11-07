resource "azurerm_service_plan" "app" {
  name                = local.plan_name
  resource_group_name = data.azurerm_resource_group.app.name
  location            = local.location
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = local.tags
}

resource "azurerm_linux_web_app" "app" {
  name                = local.web_app_name
  resource_group_name = data.azurerm_resource_group.app.name
  location            = local.location
  service_plan_id     = azurerm_service_plan.app.id
  https_only          = true
  app_settings        = local.app_settings
  tags                = local.tags

  # Deploys use GitHub OIDC + RBAC (Website Contributor), never publishing credentials.
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                         = true
    app_command_line                  = "bash startup.sh"
    ftps_state                        = "Disabled"
    minimum_tls_version               = "1.2"
    http2_enabled                     = true
    health_check_path                 = "/api/health"
    health_check_eviction_time_in_min = 10

    application_stack {
      python_version = "3.12"
    }
  }

  # "Standard App Service logs" (spec §7).
  logs {
    detailed_error_messages = false
    failed_request_tracing  = false

    application_logs {
      file_system_level = "Information"
    }

    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  lifecycle {
    precondition {
      condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.admin_bootstrap_email)) && length(var.admin_bootstrap_password) >= 12
      error_message = "Set ADMIN_BOOTSTRAP_EMAIL (a valid email, GitHub variable) and ADMIN_BOOTSTRAP_PASSWORD (secret, >=12 chars) before deploying."
    }
    precondition {
      condition     = var.admin_auth_provider != "entra" || (var.admin_entra_tenant_id != "" && var.admin_entra_client_id != "" && var.admin_entra_client_secret != "" && var.admin_entra_group_object_id != "")
      error_message = "ADMIN_AUTH_PROVIDER=entra needs the ADMIN_ENTRA_* variables/secret."
    }
    # default_hostname is only known after apply, so this cannot be a plan-time check block
    # (terraform test fails on those); a postcondition is deferred until the value is known.
    postcondition {
      condition     = "https://${self.default_hostname}" == local.public_base_url
      error_message = "PUBLIC_BASE_URL no longer matches the web app's default hostname; game links would be wrong."
    }
  }
}
