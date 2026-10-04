"""Keep tests hermetic: a developer's .env configures real Databricks and ServiceNow access,
which CI doesn't have. Environment variables take precedence over .env, so blanking them here
makes local runs behave like CI. Tests override the dependencies they need."""

import os

for name in (
    "APP_DATABRICKS_WAREHOUSE_ID",
    "APP_DATABRICKS_PROFILE",
    "SERVICENOW_INSTANCE",
    "SERVICENOW_USER",
    "SERVICENOW_PASSWORD",
    "SERVICENOW_WEBHOOK_SECRET",
    "COGNITO_USER_POOL_ID",
    "COGNITO_CLIENT_ID",
    "COGNITO_DOMAIN",
    "COGNITO_DEMO_PASSWORD",
):
    os.environ[name] = ""
