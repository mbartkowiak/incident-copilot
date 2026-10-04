#!/usr/bin/env bash
# Generates a new password for the demo accounts, stores it in Secrets Manager for the API, and
# sets it on every demo user. Run from infra/terraform after `terraform apply`; run it again to
# rotate (then redeploy the API so it reads the new value). The password is never printed, passed
# on a command line, or written to Terraform state.
set -euo pipefail

profile="${AWS_PROFILE:-incident-copilot}"
pool_id="$(terraform output -raw cognito_user_pool_id)"
secret_id="$(terraform output -raw cognito_demo_password_secret)"
users="$(terraform output -json demo_usernames | tr -d '[]" \r\n' | tr ',' ' ')"

# 192 random bits as hex, plus one of each class the password policy requires.
password="$(openssl rand -hex 24)Aa1"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"
# A native Windows AWS CLI can't read Git Bash paths such as /tmp/...
paramfile="file://$(cygpath -m "$tmp" 2>/dev/null || echo "$tmp")"

printf '{"SecretId": "%s", "SecretString": "%s"}' "$secret_id" "$password" >"$tmp"
aws secretsmanager put-secret-value --profile "$profile" --cli-input-json "$paramfile" >/dev/null
echo "stored the password in $secret_id"

for user in $users; do
  printf '{"UserPoolId": "%s", "Username": "%s", "Password": "%s", "Permanent": true}' \
    "$pool_id" "$user" "$password" >"$tmp"
  aws cognito-idp admin-set-user-password --profile "$profile" --cli-input-json "$paramfile"
  echo "set the password for $user"
done
