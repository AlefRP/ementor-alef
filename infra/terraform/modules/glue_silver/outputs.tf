output "silver_database_name" {
  description = "Database Glue/Athena da silver Data Vault."
  value       = aws_glue_catalog_database.silver_datavault.name
}

output "cold_job_name" {
  description = "Job Glue batch cold raw -> silver Data Vault."
  value       = aws_glue_job.cold_datavault.name
}

output "hot_job_name" {
  description = "Job Glue microbatch hot raw -> silver Data Vault."
  value       = aws_glue_job.hot_datavault_microbatch.name
}

output "job_failures_topic_arn" {
  description = "Topico SNS que recebe falhas/timeouts dos jobs Glue silver."
  value       = aws_sns_topic.job_failures.arn
}
