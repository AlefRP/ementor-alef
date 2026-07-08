output "producer_function_name" {
  description = "Lambda produtora de eventos sintéticos."
  value       = aws_lambda_function.producer.function_name
}

output "ingest_function_name" {
  description = "Lambda de ingestão quente (SQS -> raw)."
  value       = aws_lambda_function.ingest.function_name
}

output "event_source_mapping_uuid" {
  description = "UUID do event source mapping SQS -> ingestão."
  value       = aws_lambda_event_source_mapping.events.uuid
}
