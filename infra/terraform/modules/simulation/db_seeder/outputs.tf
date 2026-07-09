output "function_name" {
  description = "Nome da Lambda de seed do RDS (use com make seed-db)."
  value       = aws_lambda_function.seeder.function_name
}

output "function_arn" {
  description = "ARN da Lambda de seed do RDS."
  value       = aws_lambda_function.seeder.arn
}

output "role_arn" {
  description = "Role da Lambda de seed (VPC + logs)."
  value       = aws_iam_role.seeder.arn
}
