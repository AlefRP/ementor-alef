# Roles de execução — uma por serviço/função, cada uma limitada estritamente
# aos caminhos S3/filas de que precisa (princípio do menor privilégio).
# Matriz de escopo: ver .claude/skills/lakehouse-governance/SKILL.md.

locals {
  # Todas as Lambdas de ingestão escrevem SOMENTE no prefixo do seu dataset? Não:
  # o dataset é definido em runtime; o corte de menor privilégio aqui é "só PutObject,
  # só no bucket raw". Leitura/gestão ficam de fora.
  lambda_services = ["lambda.amazonaws.com"]
}

# ---------- Lambda (camada fria: EventBridge -> API -> raw) ----------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = local.lambda_services
    }
  }
}

resource "aws_iam_role" "lambda_ingest_cold" {
  name               = "${var.prefix}-lambda-ingest-cold"
  description        = "Lambda de ingestao batch (camada fria) - escreve na raw"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = var.tags
}

data "aws_iam_policy_document" "write_raw_only" {
  statement {
    sid       = "PutRawObjects"
    actions   = ["s3:PutObject"]
    resources = ["${var.raw_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "lambda_cold_raw" {
  name   = "write-raw-only"
  role   = aws_iam_role.lambda_ingest_cold.id
  policy = data.aws_iam_policy_document.write_raw_only.json
}

# Logs básicos (CloudWatch) — managed policy padrão de execução de Lambda.
resource "aws_iam_role_policy_attachment" "lambda_cold_logs" {
  role       = aws_iam_role.lambda_ingest_cold.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ---------- Lambda (camada quente: SQS -> raw) ----------
resource "aws_iam_role" "lambda_ingest_hot" {
  name               = "${var.prefix}-lambda-ingest-hot"
  description        = "Lambda de ingestao de eventos (camada quente) - consome SQS, escreve na raw"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = var.tags
}

resource "aws_iam_role_policy" "lambda_hot_raw" {
  name   = "write-raw-only"
  role   = aws_iam_role.lambda_ingest_hot.id
  policy = data.aws_iam_policy_document.write_raw_only.json
}

data "aws_iam_policy_document" "consume_events_queue" {
  statement {
    sid = "ConsumeEventsQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.events_queue_arn]
  }
}

resource "aws_iam_role_policy" "lambda_hot_sqs" {
  name   = "consume-events-queue"
  role   = aws_iam_role.lambda_ingest_hot.id
  policy = data.aws_iam_policy_document.consume_events_queue.json
}

resource "aws_iam_role_policy_attachment" "lambda_hot_logs" {
  role       = aws_iam_role.lambda_ingest_hot.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ---------- Glue (raw -> silver, Iceberg) ----------
data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_job" {
  name               = "${var.prefix}-glue-silver"
  description        = "Job Glue raw->silver (Iceberg) - le raw, escreve silver"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json

  tags = var.tags
}

data "aws_iam_policy_document" "glue_s3" {
  statement {
    sid       = "ReadRaw"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.raw_bucket_arn, "${var.raw_bucket_arn}/*"]
  }

  statement {
    sid = "ReadWriteSilver"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject", # compaction/expire snapshots do Iceberg reescrevem arquivos
      "s3:ListBucket",
    ]
    resources = [var.silver_bucket_arn, "${var.silver_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "glue_s3" {
  name   = "read-raw-write-silver"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.glue_s3.json
}

# Catálogo/logs/métricas do serviço Glue (managed padrão do serviço; o acesso
# a DADOS continua restrito pela policy acima + Lake Formation).
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_job.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# ---------- EC2 (APIs de data product) ----------
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_api" {
  name               = "${var.prefix}-ec2-api"
  description        = "EC2 das APIs - publica eventos no SQS e le o secret do RDS"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = var.tags
}

data "aws_iam_policy_document" "ec2_api" {
  statement {
    sid       = "PublishEvents"
    actions   = ["sqs:SendMessage"]
    resources = [var.events_queue_arn]
  }

  statement {
    sid       = "ReadRdsMasterSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.rds_master_secret_arn]
  }
}

resource "aws_iam_role_policy" "ec2_api" {
  name   = "publish-events-read-db-secret"
  role   = aws_iam_role.ec2_api.id
  policy = data.aws_iam_policy_document.ec2_api.json
}

resource "aws_iam_instance_profile" "ec2_api" {
  name = "${var.prefix}-ec2-api"
  role = aws_iam_role.ec2_api.name

  tags = var.tags
}
