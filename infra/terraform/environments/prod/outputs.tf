output "aws_account_id" {
  description = "Conta AWS autenticada durante o plan (valida a integração)."
  value       = data.aws_caller_identity.current.account_id
}

output "vpc_id" {
  description = "VPC do lakehouse."
  value       = module.network.vpc_id
}

output "buckets" {
  description = "Buckets por camada (raw, silver)."
  value       = module.storage.bucket_ids
}

output "events_queue_url" {
  description = "Fila de eventos da camada quente."
  value       = module.messaging.events_queue_url
}

output "database_endpoint" {
  description = "Endpoint do PostgreSQL (Olist)."
  value       = module.database.endpoint
}

output "database_master_secret_arn" {
  description = "Secret (Secrets Manager) com a senha master do RDS."
  value       = module.database.master_user_secret_arn
}

output "execution_roles" {
  description = "Roles de execução criadas pela governança."
  value = {
    lambda_ingest_cold = module.governance.lambda_ingest_cold_role_arn
    lambda_ingest_hot  = module.governance.lambda_ingest_hot_role_arn
    glue_silver        = module.governance.glue_job_role_arn
    ec2_api_profile    = module.governance.ec2_api_instance_profile_name
  }
}
