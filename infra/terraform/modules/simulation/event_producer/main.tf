# SIMULAÇÃO — não faz parte da arquitetura do lakehouse.
#
# Gera eventos sintéticos de pedidos e os publica no SQS. A arquitetura da
# camada quente começa DEPOIS: do SQS para a frente (modules/hot_ingestion).
# Num cenário real, quem publica na fila seria um sistema de origem.
#
# Roda FORA da VPC de propósito: o SQS não tem gateway endpoint gratuito, e
# daqui a fila é alcançada pelo endpoint público da AWS com TLS + IAM (a policy
# da fila nega conexões não-TLS).
#
# A role vive aqui, e não em governance: governance é a governança do data
# lake (roles das camadas fria/quente, Glue, EC2), não da simulação.

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "producer" {
  name               = "${var.prefix}-sim-event-producer"
  description        = "Simulacao: Lambda que publica eventos sinteticos no SQS"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = var.tags
}

data "aws_iam_policy_document" "publish_events_only" {
  statement {
    sid       = "PublishEvents"
    actions   = ["sqs:SendMessage"]
    resources = [var.events_queue_arn]
  }
}

resource "aws_iam_role_policy" "publish_events_only" {
  name   = "publish-events-only"
  role   = aws_iam_role.producer.id
  policy = data.aws_iam_policy_document.publish_events_only.json
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.producer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "xray" {
  role       = aws_iam_role.producer.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Zipa o pacote simulation/ + Faker (make event-producer-bundle). archive_file
# roda no plan/apply (não no validate), então o build só é exigido ali.
data "archive_file" "producer" {
  type        = "zip"
  source_dir  = var.build_dir
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
  description   = "Simulacao: gera eventos sinteticos de pedidos e publica no SQS"
  role          = aws_iam_role.producer.arn

  filename         = data.archive_file.producer.output_path
  source_code_hash = data.archive_file.producer.output_base64sha256
  handler          = "simulation.event_producer.handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]

  timeout     = 60
  memory_size = 128

  # -1 (sem reserva) por padrão: cabe na quota do free tier. O EventBridge já
  # dispara uma execução por vez na cadência configurada.
  reserved_concurrent_executions = var.reserved_concurrency

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

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.prefix}-event-producer"
  description         = "Cadencia do gerador de eventos (simulacao)"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "producer" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.producer.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.producer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
