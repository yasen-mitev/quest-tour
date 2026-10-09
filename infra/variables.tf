variable "app_name" {
  description = "Short globally-unique name; resources become app-<name>, psql-<name>, st<name>."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,18}[a-z0-9]$", var.app_name))
    error_message = "3-20 chars: lowercase letters, digits, hyphens; start with a letter."
  }
}

variable "resource_group_name" {
  description = "App resource group, created by infra/bootstrap/bootstrap.sh."
  type        = string
}

variable "admin_principal_object_id" {
  description = "Entra object ID of the admin (user or group): PostgreSQL Entra admin + blob access for sync-config."
  type        = string
}

variable "admin_principal_name" {
  description = "UPN (user) or display name (group) of the admin; it is the PostgreSQL role name."
  type        = string
}

variable "admin_principal_type" {
  type    = string
  default = "User"
  validation {
    condition     = contains(["User", "Group"], var.admin_principal_type)
    error_message = "User or Group."
  }
}

variable "admin_ip_addresses" {
  description = "PostgreSQL firewall: name => public IPv4 or CIDR range (e.g. 198.51.100.0/24) of an admin machine (sync-config, db-setup)."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for k, ip in var.admin_ip_addresses : can(regex("^[A-Za-z0-9_-]+$", k)) && (can(cidrhost(ip, 0)) || can(cidrhost("${ip}/32", 0)))])
    error_message = "Keys: letters, digits, - or _; values: an IPv4 address or a CIDR range (e.g. 203.0.113.0/24)."
  }
}

variable "host_principal_object_ids" {
  description = "Entra object IDs (users/groups) of host staff: read/delete photos (spec §6)."
  type        = list(string)
  default     = []
}

variable "deploy_principal_object_id" {
  description = "Object ID of the questtour-gh-deploy service principal (printed by bootstrap.sh)."
  type        = string
}

variable "admin_entra_tenant_id" {
  description = "Entra tenant hosting the admin panel client app."
  type        = string
}

variable "admin_entra_client_id" {
  description = "Application (client) ID of the admin panel Entra app registration."
  type        = string
}

variable "admin_entra_client_secret" {
  description = "Client secret of the admin panel Entra app registration."
  type        = string
  sensitive   = true
}

variable "admin_entra_group_object_id" {
  description = "Entra group allowed to use the admin panel."
  type        = string
}

variable "admin_session_secret" {
  description = ">=32-byte random secret signing admin session cookies."
  type        = string
  sensitive   = true
}

variable "budget_amount" {
  type    = number
  default = 45
}

variable "budget_contact_emails" {
  type = list(string)
  validation {
    condition     = length(var.budget_contact_emails) > 0
    error_message = "At least one e-mail address for budget alerts."
  }
}

variable "budget_start_date" {
  description = "Optional override (first day of a month, RFC 3339). Default: first day of the month of the first apply. Only read on create."
  type        = string
  default     = null
  validation {
    condition     = var.budget_start_date == null || can(regex("^\\d{4}-\\d{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "Must be the first day of a month, e.g. 2026-10-01T00:00:00Z."
  }
}

variable "db_name" {
  type    = string
  default = "questtour"
}

variable "db_owner_role" {
  type    = string
  default = "questtour_owner"
}
