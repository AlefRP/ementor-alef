output "aws_account_id" {
  description = "Conta AWS autenticada durante o plan (valida a integração)."
  value       = data.aws_caller_identity.current.account_id
}

output "vpc_id" {
  description = "VPC do lakehouse."
  value       = module.network.vpc_id
}

output "db_seeder_function_name" {
  description = "Simulação: Lambda que aplica schema, semeia o RDS e cria o api_reader (make seed-db)."
  value       = module.sim_db_seeder.function_name
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

output "api_cold_private_dns" {
  description = "DNS privado da EC2 da API fria (consumido pela Lambda na VPC)."
  value       = module.api_cold.private_dns
}

output "api_events_base_url" {
  description = "URL privada da Event API (camada quente) — fronteira de entrada dos eventos."
  value       = module.api_events.base_url
}

output "ingest_cold_function" {
  description = "Lambda de ingestão fria (EventBridge -> API -> raw)."
  value       = module.ingestion_cold.function_name
}

output "event_producer_function" {
  description = "Simulação: Lambda que gera eventos e os entrega à Event API."
  value       = module.sim_event_producer.function_name
}

output "ingest_hot_function" {
  description = "Lambda de ingestão quente (SQS -> raw)."
  value       = module.ingestion_hot.ingest_function_name
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

output "silver_datavault" {
  description = "Recursos Glue da camada silver Data Vault."
  value = {
    database     = module.silver_datavault.silver_database_name
    cold_job     = module.silver_datavault.cold_job_name
    hot_job      = module.silver_datavault.hot_job_name
    alerts_topic = module.silver_datavault.job_failures_topic_arn
  }
}

# Consumido por scripts/athena/apply_views.py e run_query.py (--tf-dir).
output "gold" {
  description = "Camada gold: database das views e workgroup do consumo analítico."
  value = {
    database  = module.gold.gold_database_name
    workgroup = module.gold.workgroup_name
    results   = module.gold.results_location
  }
}

output "observability" {
  description = "Alarmes do CloudWatch e tópico de alerta operacional."
  value = {
    alerts_topic = module.observability.alerts_topic_arn
    alarms       = module.observability.alarm_names
  }
}
