resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

data "aws_secretsmanager_secret" "databricks_client_secret" {
  name = var.databricks_client_secret_name
}

data "aws_secretsmanager_secret" "anthropic_api_key" {
  name = var.anthropic_api_key_secret_name
}

data "aws_secretsmanager_secret" "servicenow_password" {
  name = var.servicenow_password_secret_name
}

data "aws_secretsmanager_secret" "servicenow_webhook_secret" {
  name = var.servicenow_webhook_secret_name
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-api"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "main" {
  name = var.project
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Used by the ECS agent to pull the image, write logs, and inject secrets.
resource "aws_iam_role" "task_execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name = "read-app-secrets"
  role = aws_iam_role.task_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        data.aws_secretsmanager_secret.databricks_client_secret.arn,
        data.aws_secretsmanager_secret.anthropic_api_key.arn,
        data.aws_secretsmanager_secret.servicenow_password.arn,
        data.aws_secretsmanager_secret.servicenow_webhook_secret.arn,
      ]
    }]
  })
}

# Identity of the running app. No AWS permissions yet; it only calls Databricks.
resource "aws_iam_role" "task" {
  name               = "${var.project}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 1024 # the routing model (scikit-learn + MLflow) needs more than 512 MB
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name         = "api"
    image        = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "APP_ENVIRONMENT", value = "production" },
      { name = "APP_CORS_ORIGINS", value = jsonencode(["https://${aws_cloudfront_distribution.web.domain_name}"]) },
      { name = "APP_DATABRICKS_WAREHOUSE_ID", value = var.databricks_warehouse_id },
      { name = "APP_WARM_CACHE_ON_STARTUP", value = "true" },
      # Gold tables only change when the pipeline runs, so a long TTL keeps the demo fast.
      { name = "APP_METRICS_CACHE_TTL_SECONDS", value = "21600" },
      { name = "DATABRICKS_HOST", value = var.databricks_host },
      { name = "DATABRICKS_CLIENT_ID", value = var.databricks_client_id },
      { name = "SERVICENOW_INSTANCE", value = var.servicenow_instance },
      { name = "SERVICENOW_USER", value = var.servicenow_user },
    ]
    secrets = [
      { name = "DATABRICKS_CLIENT_SECRET", valueFrom = data.aws_secretsmanager_secret.databricks_client_secret.arn },
      { name = "ANTHROPIC_API_KEY", valueFrom = data.aws_secretsmanager_secret.anthropic_api_key.arn },
      { name = "SERVICENOW_PASSWORD", valueFrom = data.aws_secretsmanager_secret.servicenow_password.arn },
      { name = "SERVICENOW_WEBHOOK_SECRET", valueFrom = data.aws_secretsmanager_secret.servicenow_webhook_secret.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_security_group" "api_task" {
  name        = "${var.project}-api-task"
  description = "API tasks: inbound only from the ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "ECR, CloudWatch, Secrets Manager, Databricks"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_service" "api" {
  name                              = "${var.project}-api"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.api.arn
  desired_count                     = 1
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.api_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # CI registers new task definition revisions on every deploy.
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}
