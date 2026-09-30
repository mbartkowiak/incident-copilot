variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "incident-copilot"
}

variable "github_oidc_sub_prefix" {
  description = "Immutable OIDC subject prefix (owner@id/repo@id) of the repo allowed to deploy; see GET /repos/{repo}/actions/oidc/customization/sub"
  type        = string
  default     = "repo:mbartkowiak@1582166/incident-copilot@1396648309"
}

variable "image_tag" {
  description = "API image tag for the initial task definition; CI deploys later revisions"
  type        = string
  default     = "bootstrap"
}

variable "databricks_host" {
  type    = string
  default = "https://dbc-9b2a0073-968c.cloud.databricks.com"
}

variable "databricks_client_id" {
  description = "Application ID of the incident-copilot-api service principal (not secret)"
  type        = string
  default     = "983501ce-ccc7-4eb2-b9ca-6e10f600f8b2"
}

variable "databricks_warehouse_id" {
  type    = string
  default = "1ace299486bf57e9"
}

variable "anthropic_api_key_secret_name" {
  description = "Secrets Manager secret holding the Claude API key (created out-of-band so it never enters state)"
  type        = string
  default     = "incident-copilot/anthropic-api-key"
}

variable "servicenow_instance" {
  description = "ServiceNow instance the connector syncs with; empty disables the connector"
  type        = string
  default     = "https://dev343808.service-now.com"
}

variable "servicenow_user" {
  description = "ServiceNow integration user (itil role only; not secret)"
  type        = string
  default     = "copilot.integration"
}

variable "servicenow_password_secret_name" {
  description = "Secrets Manager secret holding the integration user's password (created out-of-band so it never enters state)"
  type        = string
  default     = "incident-copilot/servicenow-password"
}

variable "databricks_client_secret_name" {
  description = "Secrets Manager secret holding the SP OAuth secret (created out-of-band so it never enters state)"
  type        = string
  default     = "incident-copilot/databricks-client-secret"
}
