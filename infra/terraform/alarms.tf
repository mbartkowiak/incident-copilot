# Alarms for running the live service: is it up, is it failing, is the AI spend on budget, is
# the ServiceNow sync working. Each emails the address in var.alarm_email when it fires and
# when it recovers. The address is passed at apply time, never committed.
#
# Expected noise: "api-down" fires while the service is deliberately scaled to 0.

locals {
  metric_namespace = "IncidentCopilot"
  alarm_actions    = [aws_sns_topic.alarms.arn]
}

resource "aws_sns_topic" "alarms" {
  name = "${var.project}-alarms"
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email" # AWS emails a confirmation link; alarms arrive once it is clicked
  endpoint  = var.alarm_email
}

# --- metrics from the API's logs ----------------------------------------------------------------

# Every Claude call logs one telemetry line with its cost (app/telemetry.py).
resource "aws_cloudwatch_log_metric_filter" "claude_spend" {
  name           = "claude-spend"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "{ $.cost_usd > 0 }"

  metric_transformation {
    name      = "ClaudeSpendUSD"
    namespace = local.metric_namespace
    value     = "$.cost_usd"
    unit      = "None"
  }
}

resource "aws_cloudwatch_log_metric_filter" "servicenow_errors" {
  name           = "servicenow-errors"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "{ $.event = \"servicenow_error\" }"

  metric_transformation {
    name      = "ServiceNowErrors"
    namespace = local.metric_namespace
    value     = "1"
  }
}

# Application log lines at ERROR, including unhandled exceptions ("ERROR <logger>: ...").
resource "aws_cloudwatch_log_metric_filter" "app_errors" {
  name           = "app-errors"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "ERROR"

  metric_transformation {
    name      = "AppErrors"
    namespace = local.metric_namespace
    value     = "1"
  }
}

# --- alarms -------------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_down" {
  alarm_name          = "${var.project}-api-down"
  alarm_description   = "No healthy API task behind the load balancer for 5 minutes: the site's data and AI features are down. Expected while the service is scaled to 0."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.project}-api-5xx"
  alarm_description   = "The API returned 10 or more 5xx responses in 5 minutes. Check the log group for ERROR lines."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 10
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "app_errors" {
  alarm_name          = "${var.project}-app-errors"
  alarm_description   = "5 or more ERROR log lines in 5 minutes (failed Claude, Databricks or ServiceNow calls, or unhandled exceptions)."
  namespace           = local.metric_namespace
  metric_name         = aws_cloudwatch_log_metric_filter.app_errors.metric_transformation[0].name
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "claude_spend" {
  alarm_name          = "${var.project}-claude-daily-spend"
  alarm_description   = "Claude spend over the last 24 hours passed $${var.daily_claude_budget_usd}. The API's daily rate limits cap it; this says they are being reached. Set a hard monthly limit in the Anthropic console as well."
  namespace           = local.metric_namespace
  metric_name         = aws_cloudwatch_log_metric_filter.claude_spend.metric_transformation[0].name
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.daily_claude_budget_usd
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "servicenow_sync" {
  alarm_name          = "${var.project}-servicenow-sync-failing"
  alarm_description   = "5 or more ServiceNow errors in 15 minutes: the sync is failing (instance asleep, credentials expired, or an API change). PDIs hibernate after inactivity; wake it from developer.servicenow.com."
  namespace           = local.metric_namespace
  metric_name         = aws_cloudwatch_log_metric_filter.servicenow_errors.metric_transformation[0].name
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}
