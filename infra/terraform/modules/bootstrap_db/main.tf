# Bootstrap do banco de origem (camada fria). Existe porque o RDS é 100%
# privado e a EC2 da API não alcança o Secrets Manager (só o gateway endpoint
# de S3 é gratuito). Esta Lambda roda na VPC — logo enxerga o RDS pelo SG — e
# recebe a senha do master como variável de ambiente, injetada pelo Terraform
# a partir do secret gerenciado do RDS. Alternativa seria um interface endpoint
# de Secrets Manager (~US$7/mês), fora da proposta de custo zero.
#
# Não é agendada: invoque sob demanda (aws lambda invoke). É idempotente —
# schema com IF NOT EXISTS, seed que sai cedo se já há pedidos, e o
# create_api_reader guardado por DO $$.

data "archive_file" "bootstrap" {
  type        = "zip"
  source_dir  = var.build_dir
  output_path = "${path.module}/build/${var.prefix}-bootstrap-db.zip"
}

resource "aws_cloudwatch_log_group" "bootstrap" {
  #checkov:skip=CKV_AWS_158: chave gerenciada da AWS; CMK dedicada tem custo fixo sem ganho para logs de lab
  name              = "/aws/lambda/${var.prefix}-bootstrap-db"
  retention_in_days = 365

  tags = var.tags
}

resource "aws_lambda_function" "bootstrap" {
  #checkov:skip=CKV_AWS_116: invocada manualmente e idempotente; DLQ nao agrega (basta reinvocar)
  #checkov:skip=CKV_AWS_173: a senha do master vem cifrada em repouso pela chave gerenciada da Lambda; CMK dedicada tem custo fixo
  #checkov:skip=CKV_AWS_272: deploy via Terraform com source_code_hash; code signing fora do escopo da mentoria
  function_name = "${var.prefix}-bootstrap-db"
  description   = "Aplica schema, semeia dados sinteticos e cria o api_reader"
  role          = var.role_arn

  filename         = data.archive_file.bootstrap.output_path
  source_code_hash = data.archive_file.bootstrap.output_base64sha256
  handler          = "bootstrap_db.handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"] # casa com o alvo aarch64 do bundle

  # Seed de milhares de linhas via COPY: generoso no tempo, modesto na memória.
  timeout     = var.timeout_seconds
  memory_size = var.memory_mb

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
      PGHOST         = var.pghost
      PGPORT         = tostring(var.pgport)
      PGDATABASE     = var.pgdatabase
      PGUSER         = var.pguser
      PGPASSWORD     = var.pgpassword
      SEED_ORDERS    = tostring(var.seed_orders)
      SEED_CUSTOMERS = tostring(var.seed_customers)
    }
  }

  depends_on = [aws_cloudwatch_log_group.bootstrap]

  tags = var.tags
}
