#!/usr/bin/env bash
# Generates a new password for the demo accounts, stores it in Secrets Manager for the API, and
# sets it on every demo user. Run from infra/terraform after `terraform apply`; run it again to
# rotate (then redeploy the API so it reads the new value). The password is never printed, passed
# on a command line, or written to Terraform state.
set -euo pipefail

profile="${AWS_PROFILE:-incident-copilot}"
pool_id="$(terraform output -raw cognito_user_pool_id)"
secret_id="$(terraform output -raw cognito_demo_password_secret)"
users="$(terraform output -json demo_usernames | tr -d '[]" ' | tr ',' ' ')"

# 40 random alphanumerics plus one of each class the password policy requires.
password="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)Aa1"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"

printf '{"SecretId": "%s", "SecretString": "%s"}' "$secret_id" "$password" >"$tmp"
aws secretsmanager put-secret-value --profile "$profile" --cli-input-json "file://$tmp" >/dev/null
echo "stored the password in $secret_id"

for user in $users; do
  printf '{"UserPoolId": "%s", "Username": "%s", "Password": "%s", "Permanent": true}' \
    "$pool_id" "$user" "$password" >"$tmp"
  aws cognito-idp admin-set-user-password --profile "$profile" --cli-input-json "file://$tmp"
  echo "set the password for $user"
done
