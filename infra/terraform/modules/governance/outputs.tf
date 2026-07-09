output "lakeformation_data_access_role_arn" {
  description = "Role usada pelo Lake Formation para os data lake locations."
  value       = aws_iam_role.lakeformation_data_access.arn
}

output "lambda_ingest_cold_role_arn" {
  description = "Role da Lambda de ingestão batch (camada fria)."
  value       = aws_iam_role.lambda_ingest_cold.arn
}

output "lambda_ingest_hot_role_arn" {
  description = "Role da Lambda de ingestão de eventos (camada quente)."
  value       = aws_iam_role.lambda_ingest_hot.arn
}

output "lambda_event_producer_role_arn" {
  description = "Role da Lambda produtora de eventos sintéticos."
  value       = aws_iam_role.lambda_event_producer.arn
}

output "lambda_bootstrap_db_role_arn" {
  description = "Role da Lambda de bootstrap do banco (VPC + logs)."
  value       = aws_iam_role.lambda_bootstrap_db.arn
}

output "glue_job_role_arn" {
  description = "Role do job Glue raw->silver."
  value       = aws_iam_role.glue_job.arn
}

output "ec2_api_instance_profile_name" {
  description = "Instance profile das EC2 das APIs."
  value       = aws_iam_instance_profile.ec2_api.name
}
