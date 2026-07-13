output "events_queue_arn" {
  description = "ARN da fila de eventos (consumido pelas roles em governance)."
  value       = aws_sqs_queue.events.arn
}

output "events_queue_url" {
  description = "URL da fila de eventos (config da API produtora)."
  value       = aws_sqs_queue.events.url
}

output "events_dlq_arn" {
  description = "ARN da DLQ de eventos."
  value       = aws_sqs_queue.events_dlq.arn
}

output "events_queue_name" {
  description = "Nome da fila de eventos (dimensão das métricas no CloudWatch)."
  value       = aws_sqs_queue.events.name
}

output "events_dlq_name" {
  description = "Nome da DLQ (dimensão das métricas no CloudWatch)."
  value       = aws_sqs_queue.events_dlq.name
}
