output "gold_database_name" {
  description = "Database da camada gold no catálogo Glue."
  value       = aws_glue_catalog_database.gold.name
}

output "workgroup_name" {
  description = "Workgroup do Athena usado pelo consumo da gold."
  value       = aws_athena_workgroup.gold.name
}

output "results_location" {
  description = "Prefixo S3 onde o Athena grava os resultados das queries."
  value       = "s3://${var.artifacts_bucket}/athena-results/"
}
