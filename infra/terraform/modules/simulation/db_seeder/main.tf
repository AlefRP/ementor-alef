# SIMULAÇÃO — não faz parte da arquitetura do lakehouse.
#
# Prepara e alimenta o banco de origem: aplica o schema, gera dados sintéticos
# do Olist e cria o usuário de leitura da API. A arquitetura da camada fria
# começa DEPOIS: do RDS para a frente (API de data product -> lambda_ingest).
# Num cenário real, o RDS já viria populado pelo sistema transacional.
#
# Roda DENTRO da VPC porque o RDS é privado; a senha do master chega como env
# var, injetada pelo Terraform a partir do secret gerenciado. Assim a função não
# precisa de rota até o Secrets Manager, que exigiria um interface endpoint pago.
#
# Roda automaticamente no apply que cria a infra (aws_lambda_invocation) e de
# novo se o RDS for recriado; make seed-db continua valendo para re-execução
# manual. É idempotente — schema com IF NOT EXISTS, seed que sai cedo se já há
# pedidos, create_api_reader guardado.
#
# A role vive aqui, e não em governance: governance cuida das roles da
# arquitetura (camadas fria/quente, Glue, EC2), não da simulação.

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "seeder" {
  name               = "${var.prefix}-sim-db-seeder"
  description        = "Simulacao: Lambda que aplica schema, semeia o RDS e cria o api_reader"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.seeder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.seeder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "archive_file" "seeder" {
  type        = "zip"
  source_dir  = var.build_dir
  output_path = "${path.module}/build/${var.prefix}-db-seeder.zip"
}

resource "aws_cloudwatch_log_group" "seeder" {
  #checkov:skip=CKV_AWS_158: chave gerenciada da AWS; CMK dedicada tem custo fixo sem ganho para logs de lab
  name              = "/aws/lambda/${var.prefix}-db-seeder"
  retention_in_days = 365

  tags = var.tags
}

resource "aws_lambda_function" "seeder" {
  #checkov:skip=CKV_AWS_116: invocada manualmente e idempotente; DLQ nao agrega (basta reinvocar)
  #checkov:skip=CKV_AWS_173: a senha do master vem cifrada em repouso pela chave gerenciada da Lambda; CMK dedicada tem custo fixo
  #checkov:skip=CKV_AWS_272: deploy via Terraform com source_code_hash; code signing fora do escopo da mentoria
  function_name = "${var.prefix}-db-seeder"
  description   = "Simulacao: aplica schema, semeia dados sinteticos e cria o api_reader"
  role          = aws_iam_role.seeder.arn

  filename         = data.archive_file.seeder.output_path
  source_code_hash = data.archive_file.seeder.output_base64sha256
  handler          = "simulation.db_seeder.handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"] # casa com o alvo aarch64 do bundle

  # Seed de dezenas de milhares de linhas via COPY: generoso no tempo.
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

  depends_on = [aws_cloudwatch_log_group.seeder]

  tags = var.tags
}

# Bootstrap no apply: sem esta invocação o banco nasce vazio (sem schema e sem
# api_reader) e a camada fria inteira fica muda — API responde 500 e a Lambda
# de ingestão não grava nada. CREATE_ONLY roda uma vez na criação; o trigger em
# pghost re-executa quando o RDS é recriado (endpoint novo = banco vazio).
resource "aws_lambda_invocation" "bootstrap" {
  function_name   = aws_lambda_function.seeder.function_name
  input           = jsonencode({ source = "terraform-apply" })
  lifecycle_scope = "CREATE_ONLY"

  triggers = {
    pghost = var.pghost
    # Schema/seed novos re-rodam o bootstrap (idempotente): é assim que uma
    # migração de schema (ex.: coluna nova) chega a um banco já semeado.
    bundle_hash = data.archive_file.seeder.output_base64sha256
  }
}
