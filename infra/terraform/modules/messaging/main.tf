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

# Criptografia em trânsito obrigatória (custo zero): o producer fala com a fila
# pelo endpoint público da AWS (sem VPC endpoint pago), então travamos o acesso
# a HTTPS/TLS. Statement Deny com aws:SecureTransport=false é o padrão AWS —
# quem NÃO usar TLS é barrado, independente da identidade. O acesso positivo
# continua vindo das roles (least-privilege em governance/roles.tf).
data "aws_iam_policy_document" "events_tls_only" {
  statement {
    sid       = "DenyNonTLS"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.events.arn]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "events_tls_only" {
  queue_url = aws_sqs_queue.events.id
  policy    = data.aws_iam_policy_document.events_tls_only.json
}

data "aws_iam_policy_document" "events_dlq_tls_only" {
  statement {
    sid       = "DenyNonTLS"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.events_dlq.arn]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "events_dlq_tls_only" {
  queue_url = aws_sqs_queue.events_dlq.id
  policy    = data.aws_iam_policy_document.events_dlq_tls_only.json
}
