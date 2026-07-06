# Fila de eventos da camada quente: API (EC2) publica, Lambda consome e
# persiste na raw. Mensagens que falham repetidamente caem na DLQ para
# inspeção (nunca se perdem silenciosamente).
resource "aws_sqs_queue" "events_dlq" {
  name                      = "${var.prefix}-events-dlq"
  message_retention_seconds = 1209600 # 14 dias: janela máxima p/ investigar falhas
  sqs_managed_sse_enabled   = true

  tags = merge(var.tags, { Name = "${var.prefix}-events-dlq" })
}

resource "aws_sqs_queue" "events" {
  name                       = "${var.prefix}-events"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = 345600 # 4 dias
  receive_wait_time_seconds  = 10     # long polling: menos receives vazios
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(var.tags, { Name = "${var.prefix}-events" })
}

# DLQ só recebe mensagens da fila principal (evita uso indevido).
resource "aws_sqs_queue_redrive_allow_policy" "events_dlq" {
  queue_url = aws_sqs_queue.events_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.events.arn]
  })
}
