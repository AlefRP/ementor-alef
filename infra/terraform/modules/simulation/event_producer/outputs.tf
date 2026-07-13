output "function_name" {
  description = "Nome da Lambda produtora de eventos (simulação)."
  value       = aws_lambda_function.producer.function_name
}

output "role_arn" {
  description = "Role da Lambda produtora (só logs e ENI na VPC — sem acesso ao SQS)."
  value       = aws_iam_role.producer.arn
}
