mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      client_id       = "00000000-0000-0000-0000-000000000003"
      object_id       = "00000000-0000-0000-0000-000000000004"
    }
  }
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-qt-test"
      location = "westeurope"
    }
  }
}

variables {
  app_name                    = "qt-test"
  resource_group_name         = "rg-qt-test"
  admin_principal_object_id   = "11111111-1111-1111-1111-111111111111"
  admin_principal_name        = "admin_contoso.com#EXT#@tenant.onmicrosoft.com"
  admin_ip_addresses          = { home = "203.0.113.10" }
  host_principal_object_ids   = ["33333333-3333-3333-3333-333333333333"]
  budget_contact_emails       = ["ops@contoso.com"]
  deploy_principal_object_id  = "22222222-2222-2222-2222-222222222222"
  admin_entra_tenant_id       = "00000000-0000-0000-0000-000000000010"
  admin_entra_client_id       = "00000000-0000-0000-0000-000000000011"
  admin_entra_client_secret   = "test-client-secret"
  admin_entra_group_object_id = "44444444-4444-4444-4444-444444444444"
  admin_session_secret        = "test-session-secret-at-least-32-chars-long"
}

run "prod_shape" {
  command = plan

  assert {
    condition     = azurerm_linux_web_app.app.name == "app-qt-test"
    error_message = "web app name must be app-<app_name> (PUBLIC_BASE_URL and DATABASE_URL depend on it)"
  }
  assert {
    condition     = azurerm_linux_web_app.app.site_config[0].app_command_line == "bash startup.sh"
    error_message = "migrations run in the startup command"
  }
  assert {
    condition     = azurerm_linux_web_app.app.site_config[0].application_stack[0].python_version == "3.12"
    error_message = "runtime must be Python 3.12"
  }
  assert {
    condition = (
      azurerm_linux_web_app.app.app_settings["DATABASE_AUTH"] == "azure_ad" &&
      azurerm_linux_web_app.app.app_settings["DATABASE_URL"] == "postgresql+psycopg://app-qt-test@psql-qt-test.postgres.database.azure.com:5432/questtour?sslmode=require" &&
      azurerm_linux_web_app.app.app_settings["DATABASE_OWNER_ROLE"] == "questtour_owner" &&
      azurerm_linux_web_app.app.app_settings["PUBLIC_BASE_URL"] == "https://app-qt-test.azurewebsites.net" &&
      azurerm_linux_web_app.app.app_settings["AZURE_STORAGE_ACCOUNT_URL"] == "https://stqttest.blob.core.windows.net" &&
      azurerm_linux_web_app.app.app_settings["STATIC_DIR"] == "static" &&
      azurerm_linux_web_app.app.app_settings["SCM_DO_BUILD_DURING_DEPLOYMENT"] == "true" &&
      azurerm_linux_web_app.app.app_settings["ADMIN_AUTH_PROVIDER"] == "entra" &&
      azurerm_linux_web_app.app.app_settings["ADMIN_SESSION_SECURE"] == "true" &&
      azurerm_linux_web_app.app.app_settings["ADMIN_ENTRA_REDIRECT_URI"] == "https://app-qt-test.azurewebsites.net/api/admin/auth/callback" &&
      azurerm_linux_web_app.app.app_settings["ADMIN_ENTRA_GROUP_OBJECT_ID"] == "44444444-4444-4444-4444-444444444444"
    )
    error_message = "app settings must match what questtour.settings and startup.sh expect"
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.db.authentication[0].password_auth_enabled == false && azurerm_postgresql_flexible_server.db.authentication[0].active_directory_auth_enabled == true
    error_message = "PostgreSQL must be Entra-only"
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.db.backup_retention_days == 7
    error_message = "spec §7: 7-day PostgreSQL backups"
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.azure_services.start_ip_address == "0.0.0.0" && length(azurerm_postgresql_flexible_server_firewall_rule.admin) == 1
    error_message = "firewall: Azure services + one rule per admin IP"
  }
  assert {
    condition     = azurerm_storage_account.main.shared_access_key_enabled == false && azurerm_storage_account.main.allow_nested_items_to_be_public == false
    error_message = "storage must be Entra/RBAC-only and private"
  }
  assert {
    condition     = azurerm_storage_account.main.blob_properties[0].delete_retention_policy[0].days == 14 && azurerm_storage_account.main.blob_properties[0].container_delete_retention_policy[0].days == 14
    error_message = "spec §7: 14-day soft delete"
  }
  assert {
    condition     = azurerm_consumption_budget_resource_group.monthly.amount == 45
    error_message = "spec §7: €45 budget alert"
  }
  assert {
    condition     = can(regex("^\\d{4}-\\d{2}-01T00:00:00Z$", azurerm_consumption_budget_resource_group.monthly.time_period[0].start_date))
    error_message = "by default the budget starts on the first day of the current month"
  }
  assert {
    condition     = length(azurerm_role_assignment.host_photos) == 1 && azurerm_role_assignment.deploy.role_definition_name == "Website Contributor"
    error_message = "hosts get photo access; the deploy identity only Website Contributor"
  }
  assert {
    condition     = strcontains(output.admin_sync_config_env, "postgresql+psycopg://admin_contoso.com%23EXT%23%40tenant.onmicrosoft.com@psql-qt-test.")
    error_message = "the admin DATABASE_URL must URL-encode guest UPNs (#EXT#)"
  }
}

run "budget_start_override" {
  command = plan

  variables {
    budget_start_date = "2027-01-01T00:00:00Z"
  }

  assert {
    condition     = azurerm_consumption_budget_resource_group.monthly.time_period[0].start_date == "2027-01-01T00:00:00Z"
    error_message = "budget_start_date overrides the computed default"
  }
}

run "cidr_admin_rules" {
  command = plan

  variables {
    admin_ip_addresses = {
      home = "203.0.113.10"
      site = "198.51.100.0/24"
    }
  }

  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.admin["home"].start_ip_address == "203.0.113.10"
    error_message = "a bare IPv4 becomes a single-host rule"
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.admin["site"].start_ip_address == "198.51.100.0" && azurerm_postgresql_flexible_server_firewall_rule.admin["site"].end_ip_address == "198.51.100.255"
    error_message = "a CIDR becomes network address .. broadcast"
  }
}

run "rejects_bad_app_name" {
  command = plan

  variables {
    app_name = "Bad_Name"
  }

  expect_failures = [var.app_name]
}
