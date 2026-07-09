output "function_name" {
  description = "Nome da Lambda de bootstrap (use com aws lambda invoke)."
  value       = aws_lambda_function.bootstrap.function_name
}

output "function_arn" {
  description = "ARN da Lambda de bootstrap."
  value       = aws_lambda_function.bootstrap.arn
}
