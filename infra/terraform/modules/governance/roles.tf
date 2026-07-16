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

# A Lambda fria roda DENTRO da VPC (tráfego privado até a API/S3); a managed
# policy concede a gestão de ENIs que o serviço exige nesse modo.
resource "aws_iam_role_policy_attachment" "lambda_cold_vpc" {
  role       = aws_iam_role.lambda_ingest_cold.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# O marker de retomada (_markers/<dataset>.json) é lido no início de cada
# execução — GetObject restrito ao prefixo de markers, nada além.
data "aws_iam_policy_document" "read_markers_only" {
  statement {
    sid       = "ReadIngestionMarkers"
    actions   = ["s3:GetObject"]
    resources = ["${var.raw_bucket_arn}/_markers/*"]
  }

  # Na primeira execução o marker não existe. Sem ListBucket, o S3 responde
  # AccessDenied (403) em vez de NoSuchKey (404) para chave inexistente — e o
  # handler, que trata o 404 como "começar do início", quebraria. A ação vai no
  # ARN do bucket e SEM condition: a checagem que decide 404-vs-403 não carrega
  # a chave de contexto s3:prefix, então um StringLike nela reintroduziria o 403.
  statement {
    sid       = "ListRawToGetNotFoundOnMissingMarker"
    actions   = ["s3:ListBucket"]
    resources = [var.raw_bucket_arn]
  }
}

resource "aws_iam_role_policy" "lambda_cold_markers" {
  name   = "read-markers-only"
  role   = aws_iam_role.lambda_ingest_cold.id
  policy = data.aws_iam_policy_document.read_markers_only.json
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

# A Lambda quente também roda na VPC (S3 via gateway endpoint).
resource "aws_iam_role_policy_attachment" "lambda_hot_vpc" {
  role       = aws_iam_role.lambda_ingest_hot.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# X-Ray nas Lambdas da arquitetura (tracing_config Active exige estas permissões;
# managed policy do serviço — dados continuam restritos pelas policies acima).
# As Lambdas de simulação levam o X-Ray na própria role (modules/simulation).
resource "aws_iam_role_policy_attachment" "lambda_xray" {
  for_each = {
    cold = aws_iam_role.lambda_ingest_cold.name
    hot  = aws_iam_role.lambda_ingest_hot.name
  }

  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
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

  statement {
    sid       = "ReadGlueArtifacts"
    actions   = ["s3:GetObject"]
    resources = ["${var.artifacts_bucket_arn}/glue/*"]
  }

  statement {
    sid = "WriteGlueTemp"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.artifacts_bucket_arn}/glue/tmp/*"]
  }

  statement {
    sid       = "ListGlueArtifacts"
    actions   = ["s3:ListBucket"]
    resources = [var.artifacts_bucket_arn]
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

# A security configuration dos jobs silver cifra os logs com SSE-KMS; ao criar
# o log group, o runner do Glue chama logs:AssociateKmsKey — ação que a managed
# AWSGlueServiceRole NÃO concede (ela para em Create*/PutLogEvents). Sem isso o
# job morre no bootstrap, antes de qualquer linha do script. Escopo restrito
# aos log groups do Glue nesta conta/região.
data "aws_iam_policy_document" "glue_logs_kms" {
  statement {
    sid     = "AssociateKmsKeyOnGlueLogGroups"
    actions = ["logs:AssociateKmsKey"]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"
    ]
  }
}

resource "aws_iam_role_policy" "glue_logs_kms" {
  name   = "associate-kms-key-glue-logs"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.glue_logs_kms.json
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
  description        = "EC2 das APIs - SQS, IAM auth no RDS e bundle de deploy"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = var.tags
}

# Rede 100% privada: a API autentica no RDS com token IAM (assinado localmente,
# sem Secrets Manager) e baixa o bundle de deploy do bucket de artefatos via
# gateway endpoint. Nada de segredo em runtime.
# (data aws_caller_identity "current" já declarado em lakeformation.tf)
data "aws_region" "current" {}

data "aws_iam_policy_document" "ec2_api" {
  statement {
    sid       = "PublishEvents"
    actions   = ["sqs:SendMessage"]
    resources = [var.events_queue_arn]
  }

  statement {
    sid     = "ConnectAsApiReader"
    actions = ["rds-db:connect"]
    resources = [
      "arn:aws:rds-db:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:dbuser:${var.rds_resource_id}/${var.api_db_user}"
    ]
  }

  statement {
    sid       = "ReadDeployBundle"
    actions   = ["s3:GetObject"]
    resources = ["${var.artifacts_bucket_arn}/api/*"]
  }

  # O user_data envia /var/log/user-data.log para logs/ ao falhar (e ao concluir):
  # é o único registro de boot de uma instância privada. Bucket versionado
  # preserva o histórico mesmo com chave fixa.
  statement {
    sid       = "ShipBootLog"
    actions   = ["s3:PutObject"]
    resources = ["${var.artifacts_bucket_arn}/logs/*"]
  }
}

resource "aws_iam_role_policy" "ec2_api" {
  name   = "publish-events-iam-auth-deploy"
  role   = aws_iam_role.ec2_api.id
  policy = data.aws_iam_policy_document.ec2_api.json
}

# Session Manager: shell auditável na EC2 privada sem SSH nem IP público
# (os interface endpoints correspondentes estão no módulo network).
resource "aws_iam_role_policy_attachment" "ec2_api_ssm" {
  role       = aws_iam_role.ec2_api.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_api" {
  name = "${var.prefix}-ec2-api"
  role = aws_iam_role.ec2_api.name

  tags = var.tags
}

