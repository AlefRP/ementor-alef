# SIMULAÇÃO — não faz parte da arquitetura do lakehouse.
#
# Gera eventos sintéticos de pedidos e os entrega à EVENT API (EC2), que é a
# fronteira de entrada da camada quente. A arquitetura começa DEPOIS: Event API
# -> SQS -> Lambda -> raw. Num cenário real, quem chamaria a API seria o sistema
# de origem — este produtor ocupa esse lugar.
#
# Roda DENTRO da VPC porque a API é privada (sem IP público): alcança a EC2 pelo
# IP fixo e valida o TLS contra a CA da própria API. Ela NÃO fala com o SQS —
# publicar na fila é responsabilidade da API, não da simulação.
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
  description        = "Simulacao: Lambda que entrega eventos sinteticos a Event API"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = var.tags
}

# Sem policy própria: a simulação só faz uma chamada HTTP à API dentro da VPC.
# Não há permissão de SQS aqui — publicar na fila é da API (role ec2-api).
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.producer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ENIs nas subnets privadas (exigência de qualquer Lambda em VPC).
resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.producer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
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
  #checkov:skip=CKV_AWS_116: EventBridge ja faz retry; producer e stateless e a proxima execucao repoe os eventos
  #checkov:skip=CKV_AWS_173: variaveis de ambiente sem segredo (API_CA_PEM e certificado publico); chave gerenciada da AWS basta
  #checkov:skip=CKV_AWS_272: deploy via Terraform com source_code_hash; code signing fora do escopo da mentoria
  function_name = "${var.prefix}-event-producer"
  description   = "Simulacao: gera eventos sinteticos e entrega a Event API"
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

  # Na VPC: a Event API é privada, só alcançável de dentro dela.
  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      API_BASE_URL       = var.api_base_url
      API_CA_PEM         = var.api_ca_pem # CA self-signed da API (público)
      EVENTS_PER_RUN     = tostring(var.events_per_run)
      EVENTS_PER_REQUEST = tostring(var.events_per_request)
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
