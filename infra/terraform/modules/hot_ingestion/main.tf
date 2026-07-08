# Camada quente: EventBridge agenda a Lambda produtora (fora da VPC — o SQS
# só é alcançável de forma privada com interface endpoint pago; aqui ela usa
# o endpoint público da AWS com IAM), que publica eventos sintéticos na fila;
# o event source mapping entrega os lotes à Lambda de ingestão (na VPC), que
# grava na raw via gateway endpoint com ReportBatchItemFailures.

# ---------- Producer (EventBridge -> SQS) ----------
data "archive_file" "producer" {
  type        = "zip"
  source_file = var.producer_source
  output_path = "${path.module}/build/${var.prefix}-event-producer.zip"
}

resource "aws_cloudwatch_log_group" "producer" {
  #checkov:skip=CKV_AWS_158: chave gerenciada da AWS; CMK dedicada tem custo fixo sem ganho para logs de lab
  name              = "/aws/lambda/${var.prefix}-event-producer"
  retention_in_days = 365

  tags = var.tags
}

resource "aws_lambda_function" "producer" {
  #checkov:skip=CKV_AWS_117: fora da VPC de proposito - o SQS nao tem gateway endpoint gratuito; a funcao so fala com o SQS via TLS/IAM
  #checkov:skip=CKV_AWS_116: EventBridge ja faz retry; producer e stateless e a proxima execucao repoe os eventos
  #checkov:skip=CKV_AWS_173: variaveis de ambiente sem segredo; chave gerenciada da AWS basta
  #checkov:skip=CKV_AWS_272: deploy via Terraform com source_code_hash; code signing fora do escopo da mentoria
  function_name = "${var.prefix}-event-producer"
  description   = "Gera eventos sinteticos de pedidos e publica no SQS"
  role          = var.producer_role_arn

  filename         = data.archive_file.producer.output_path
  source_code_hash = data.archive_file.producer.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]

  timeout     = 60
  memory_size = 128

  reserved_concurrent_executions = 1

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      QUEUE_URL      = var.events_queue_url
      EVENTS_PER_RUN = tostring(var.events_per_run)
    }
  }

  depends_on = [aws_cloudwatch_log_group.producer]

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "producer_schedule" {
  name                = "${var.prefix}-event-producer"
  description         = "Cadencia do gerador de eventos da camada quente"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "producer" {
  rule = aws_cloudwatch_event_rule.producer_schedule.name
  arn  = aws_lambda_function.producer.arn
}

resource "aws_lambda_permission" "producer_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.producer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.producer_schedule.arn
}

# ---------- Ingestão (SQS -> raw) ----------
data "archive_file" "ingest" {
  type        = "zip"
  source_file = var.ingest_source
  output_path = "${path.module}/build/${var.prefix}-raw-ingest.zip"
}

resource "aws_cloudwatch_log_group" "ingest" {
  #checkov:skip=CKV_AWS_158: chave gerenciada da AWS; CMK dedicada tem custo fixo sem ganho para logs de lab
  name              = "/aws/lambda/${var.prefix}-ingest-hot"
  retention_in_days = 365

  tags = var.tags
}

resource "aws_lambda_function" "ingest" {
  #checkov:skip=CKV_AWS_116: consumo de SQS e sincrono (sem DLQ de funcao); a propria fila tem redrive para a DLQ
  #checkov:skip=CKV_AWS_173: variaveis de ambiente sem segredo; chave gerenciada da AWS basta
  #checkov:skip=CKV_AWS_272: deploy via Terraform com source_code_hash; code signing fora do escopo da mentoria
  function_name = "${var.prefix}-ingest-hot"
  description   = "Consome eventos do SQS e grava na raw (batch item failures)"
  role          = var.ingest_role_arn

  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]

  timeout     = var.ingest_timeout_seconds
  memory_size = 256

  reserved_concurrent_executions = var.ingest_max_concurrency

  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      RAW_BUCKET = var.raw_bucket
      DATASET    = var.dataset
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest]

  tags = var.tags
}

# Entrega em lotes com reporte granular: só as mensagens que falharam voltam
# para a fila (redrive -> DLQ cuida das reincidentes).
resource "aws_lambda_event_source_mapping" "events" {
  event_source_arn        = var.events_queue_arn
  function_name           = aws_lambda_function.ingest.arn
  batch_size              = var.batch_size
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.ingest_max_concurrency
  }
}
