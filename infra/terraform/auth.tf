# Sign-in (ADR 0011). Cognito is the OIDC provider the web app and API trust; an organization's
# own identity provider (Okta, Entra ID) would be federated into this pool as an extra provider.
# Groups are the app's roles.

locals {
  site_url = "https://${aws_cloudfront_distribution.web.domain_name}"
  roles    = ["employee", "dispatcher", "knowledge_manager"]

  # One-click demo accounts. Must match DEMO_ACCOUNTS in apps/api/app/routes/auth.py.
  demo_users = {
    "demo-priya"      = { name = "Priya Shah", site = "Remote", role = "employee" }
    "demo-jordan"     = { name = "Jordan Lee", site = "Memphis DC", role = "employee" }
    "demo-marcus"     = { name = "Marcus Chen", site = "Chicago HQ", role = "employee" }
    "demo-ana"        = { name = "Ana Torres", site = "Dallas DC", role = "employee" }
    "demo-dispatcher" = { name = "Sam Rivera", site = "", role = "dispatcher" }
    "demo-knowledge"  = { name = "Alex Morgan", site = "", role = "knowledge_manager" }
  }
}

resource "aws_cognito_user_pool" "users" {
  name = "${var.project}-users"

  # Accounts are created by an administrator (or federated in), never self-registered.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_configuration {
    case_sensitive = false
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 3
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Where the employee works, from the HR record in a real deployment. Users can't change it
  # (the client's write_attributes); mutable so an administrator can.
  schema {
    name                     = "site"
    attribute_data_type      = "String"
    mutable                  = true
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 0
      max_length = 100
    }
  }

  schema {
    name                     = "demo"
    attribute_data_type      = "String"
    mutable                  = true
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 0
      max_length = 5
    }
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project}-web"
  user_pool_id = aws_cognito_user_pool.users.id

  # A public client: the SPA can't keep a secret, so the hosted login uses PKCE.
  generate_secret = false
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH", # the API's demo sign-in only; the password never leaves the API
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["${local.site_url}/", "http://localhost:5173/"]
  logout_urls                          = ["${local.site_url}/", "http://localhost:5173/"]

  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 12
  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "hours"
  }

  read_attributes = ["email", "name", "custom:site", "custom:demo"]
  # Users can't rename themselves or change their site or demo flag through this client.
  write_attributes = ["email"]
}

resource "aws_cognito_user_pool_domain" "hosted" {
  domain       = "${var.project}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.users.id
}

resource "aws_cognito_user_group" "role" {
  for_each     = toset(local.roles)
  name         = each.key
  user_pool_id = aws_cognito_user_pool.users.id
}

# --- demo accounts ------------------------------------------------------------------------------

resource "aws_cognito_user" "demo" {
  for_each       = local.demo_users
  user_pool_id   = aws_cognito_user_pool.users.id
  username       = each.key
  message_action = "SUPPRESS"
  # The password is set by infra/scripts/set-demo-password.sh, so it never enters Terraform state.

  attributes = merge(
    # Custom attributes without their "custom:" prefix, as the provider stores them.
    { name = each.value.name, demo = "true" },
    each.value.site == "" ? {} : { site = each.value.site },
  )
}

resource "aws_cognito_user_in_group" "demo" {
  for_each     = local.demo_users
  user_pool_id = aws_cognito_user_pool.users.id
  username     = aws_cognito_user.demo[each.key].username
  group_name   = aws_cognito_user_group.role[each.value.role].name
}

# The API signs visitors in to the demo accounts, so it alone holds the password. The value is
# written by infra/scripts/set-demo-password.sh, never by Terraform.
resource "aws_secretsmanager_secret" "cognito_demo_password" {
  name                    = "${var.project}/cognito-demo-password"
  recovery_window_in_days = 0
}
