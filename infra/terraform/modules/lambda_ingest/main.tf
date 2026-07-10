# Lambda de ingestão fria (EventBridge -> API privada -> S3 raw). Roda DENTRO
# da VPC (subnets privadas): chama a API pelo DNS privado da EC2 e escreve no
# S3 pelo gateway endpoint — nenhum tráfego sai para a internet.

# Zip com o handler + a CA self-signed da API: a Lambda verifica o TLS da EC2
# contra este PEM (API_CA_FILE). archive_file com blocos source (content) evita
# um diretório de build intermediário.
data "archive_file" "handler" {
  type        = "zip"
  output_path = "${path.module}/build/${var.prefix}-ingest-cold.zip"

  source {
    content  = file(var.handler_source)
    filename = "handler.py"
  }

  source {
    content  = var.api_ca_pem
    filename = "api_ca.pem"
  }
}

resource "aws_cloudwatch_log_group" "this" {
  #checkov:skip=CKV_AWS_158: chave gerenciada da AWS; CMK dedicada tem custo fixo sem ganho para logs de lab
  name              = "/aws/lambda/${var.prefix}-ingest-cold"
  retention_in_days = 365

  tags = var.tags
}

resource "aws_lambda_function" "this" {
  #checkov:skip=CKV_AWS_116: batch idempotente e retomável via marker; falha fica visível no schedule e a próxima execução continua do cursor — DLQ não agrega
  #checkov:skip=CKV_AWS_173: variáveis de ambiente sem segredo (IAM auth/token na API é opcional e viria de SSM); chave gerenciada da AWS basta
  #checkov:skip=CKV_AWS_272: deploy via Terraform com source_code_hash; code signing exige AWS Signer, fora do escopo da mentoria
  function_name = "${var.prefix}-ingest-cold"
  description   = "Ingestao batch: consome a API de pedidos e grava na raw"
  role          = var.role_arn

  filename         = data.archive_file.handler.output_path
  source_code_hash = data.archive_file.handler.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"] # Graviton: mais barato por ms

  timeout     = var.timeout_seconds
  memory_size = var.memory_mb

  # Cinto de segurança do marker (cursor keyset): 1 execução por vez. Fica em -1
  # (sem reserva) por padrão para caber na quota de concorrência do free tier —
  # com schedule diário não há sobreposição de execuções de qualquer forma.
  reserved_concurrent_executions = var.reserved_concurrency

  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      API_BASE_URL = var.api_base_url
      API_CA_FILE  = "/var/task/api_ca.pem" # CA embarcada no zip (raiz da Lambda)
      RAW_BUCKET   = var.raw_bucket
      DATASET      = var.dataset
      PAGE_SIZE    = tostring(var.page_size)
      MAX_PAGES    = tostring(var.max_pages)
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.prefix}-ingest-cold"
  description         = "Agenda da ingestao batch da camada fria"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.this.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# Uma regra por dataset extra: mesma função, mesmo schedule; o input do alvo
# injeta o dataset e o modo de cursor (pk = snapshot resumível por chave
# primária, contrato dos /v1/<dataset>). O marker separa o estado por dataset.
resource "aws_cloudwatch_event_rule" "dataset" {
  for_each = toset(var.extra_datasets)

  # Nome de regra tem limite de 64 chars e datasets do Olist são longos
  # (product_category_name_translation estoura); o substr trunca com segurança
  # e o dataset íntegro segue no input do alvo, que é o que a Lambda lê.
  name                = substr("${var.prefix}-ingest-cold-${replace(each.value, "_", "-")}", 0, 64)
  description         = "Agenda da ingestao batch do dataset ${each.value}"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "dataset" {
  for_each = aws_cloudwatch_event_rule.dataset

  rule  = each.value.name
  arn   = aws_lambda_function.this.arn
  input = jsonencode({ dataset = each.key, cursor_mode = "pk" })
}

resource "aws_lambda_permission" "dataset" {
  for_each = aws_cloudwatch_event_rule.dataset

  statement_id  = "AllowEventBridge-${replace(each.key, "_", "-")}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}
