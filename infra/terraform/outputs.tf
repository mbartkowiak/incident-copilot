output "site_url" {
  value = "https://${aws_cloudfront_distribution.web.domain_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "web_bucket" {
  value = aws_s3_bucket.web.id
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.web.id
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = aws_ecs_service.api.name
}

output "task_definition_family" {
  value = aws_ecs_task_definition.api.family
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.users.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "cognito_hosted_login" {
  value = "https://${aws_cognito_user_pool_domain.hosted.domain}.auth.${var.region}.amazoncognito.com"
}

output "cognito_demo_password_secret" {
  value = aws_secretsmanager_secret.cognito_demo_password.name
}

output "demo_usernames" {
  value = keys(local.demo_users)
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}
