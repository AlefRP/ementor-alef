output "function_name" {
  description = "Nome da Lambda de ingestão fria."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN da Lambda de ingestão fria."
  value       = aws_lambda_function.this.arn
}

output "schedule_rule_arn" {
  description = "ARN da regra de agendamento (EventBridge)."
  value       = aws_cloudwatch_event_rule.schedule.arn
}
