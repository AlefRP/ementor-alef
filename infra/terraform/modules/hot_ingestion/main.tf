# Camada quente da ARQUITETURA: começa no SQS. O event source mapping entrega
# os lotes à Lambda de ingestão (na VPC), que grava na raw via gateway endpoint
# com ReportBatchItemFailures.
#
# Quem PUBLICA na fila é simulação e vive em modules/simulation/event_producer —
# fora da arquitetura, de propósito.

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

  # -1 (sem reserva) por padrão: o teto de concorrência do consumo de SQS é
  # aplicado no event source mapping (scaling_config.maximum_concurrency),
  # que não consome a cota de concorrência reservada da conta.
  reserved_concurrent_executions = var.ingest_reserved_concurrency

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
