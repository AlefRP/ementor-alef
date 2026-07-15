locals {
  script_prefix = "glue/silver"
  iceberg_conf = join(" --conf ", [
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog",
    "spark.sql.catalog.glue_catalog.warehouse=s3://${var.silver_bucket}/warehouse/",
    "spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog",
    "spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
  ])

  common_default_arguments = {
    "--TempDir"                          = "s3://${var.artifacts_bucket}/glue/tmp/"
    "--conf"                             = local.iceberg_conf
    "--datalake-formats"                 = "iceberg"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
    "--enable-job-insights"              = "true"
    "--enable-metrics"                   = "true"
    "--job-language"                     = "python"
    "--extra-py-files"                   = "s3://${var.artifacts_bucket}/${aws_s3_object.runtime.key}"
    "--raw_bucket"                       = var.raw_bucket
    "--silver_bucket"                    = var.silver_bucket
    "--silver_database"                  = aws_glue_catalog_database.silver_datavault.name
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# KEY POLICY da chave KMS — não é uma policy de identidade.
# Ela é anexada à PRÓPRIA chave, então `resources = ["*"]` significa "esta
# chave" (não existe outro recurso para apontar, e a AWS exige o "*" aqui). O
# escopo real vem dos principals: root da conta administra, a role do Glue usa
# em runtime e os serviços operacionais (EventBridge/Logs/SNS) cifram/decifram.
# Os três checks abaixo assumem policy de identidade e dão falso positivo.
data "aws_iam_policy_document" "glue_security_kms" {
  #checkov:skip=CKV_AWS_109: key policy - o "*" e a propria chave; o escopo vem dos principals
  #checkov:skip=CKV_AWS_111: key policy - idem; kms:PutKeyPolicy so para o root da conta
  #checkov:skip=CKV_AWS_356: key policy - a AWS exige Resource "*" numa policy anexada a chave
  statement {
    sid = "EnableAccountKeyAdministration"
    actions = [
      "kms:CancelKeyDeletion",
      "kms:CreateAlias",
      "kms:CreateGrant",
      "kms:DeleteAlias",
      "kms:DescribeKey",
      "kms:DisableKey",
      "kms:DisableKeyRotation",
      "kms:EnableKey",
      "kms:EnableKeyRotation",
      "kms:GetKeyPolicy",
      "kms:GetKeyRotationStatus",
      "kms:ListGrants",
      "kms:ListKeyPolicies",
      "kms:ListResourceTags",
      "kms:PutKeyPolicy",
      "kms:RevokeGrant",
      "kms:ScheduleKeyDeletion",
      "kms:TagResource",
      "kms:UntagResource",
      "kms:UpdateAlias",
      "kms:UpdateKeyDescription",
    ]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid = "AllowGlueJobRuntime"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:GenerateDataKeyPair",
      "kms:GenerateDataKeyPairWithoutPlaintext",
      "kms:GenerateDataKeyWithoutPlaintext",
      "kms:ReEncryptFrom",
      "kms:ReEncryptTo",
    ]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = [var.role_arn]
    }
  }

  statement {
    sid = "AllowOperationalServices"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:GenerateDataKeyPair",
      "kms:GenerateDataKeyPairWithoutPlaintext",
      "kms:GenerateDataKeyWithoutPlaintext",
      "kms:ReEncryptFrom",
      "kms:ReEncryptTo",
    ]
    resources = ["*"]

    principals {
      type = "Service"
      identifiers = [
        "events.amazonaws.com",
        "logs.${data.aws_region.current.name}.amazonaws.com",
        "sns.amazonaws.com",
      ]
    }
  }
}

resource "aws_kms_key" "glue_security" {
  description             = "Criptografia dos jobs Glue silver e alertas SNS"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.glue_security_kms.json

  tags = merge(var.tags, { Component = "glue-silver-security" })
}

resource "aws_kms_alias" "glue_security" {
  name          = "alias/${var.prefix}-glue-silver-security"
  target_key_id = aws_kms_key.glue_security.key_id
}

resource "aws_glue_security_configuration" "silver" {
  name = "${var.prefix}-silver-security"

  encryption_configuration {
    cloudwatch_encryption {
      cloudwatch_encryption_mode = "SSE-KMS"
      kms_key_arn                = aws_kms_key.glue_security.arn
    }

    job_bookmarks_encryption {
      job_bookmarks_encryption_mode = "CSE-KMS"
      kms_key_arn                   = aws_kms_key.glue_security.arn
    }

    s3_encryption {
      s3_encryption_mode = "SSE-KMS"
      kms_key_arn        = aws_kms_key.glue_security.arn
    }
  }
}
data "archive_file" "runtime" {
  type        = "zip"
  source_dir  = var.runtime_source_dir
  output_path = "${path.module}/build/${var.prefix}-glue-silver-runtime.zip"
}

resource "aws_glue_catalog_database" "silver_datavault" {
  name        = var.silver_database_name
  description = "Camada silver modelada como Raw Data Vault em Apache Iceberg."

  tags = var.tags
}

resource "aws_lakeformation_permissions" "glue_database" {
  principal = var.role_arn
  permissions = [
    "ALTER",
    "CREATE_TABLE",
    "DESCRIBE",
  ]

  database {
    name = aws_glue_catalog_database.silver_datavault.name
  }
}

resource "aws_lakeformation_permissions" "glue_tables" {
  principal = var.role_arn
  permissions = [
    "ALTER",
    "DELETE",
    "DESCRIBE",
    "INSERT",
    "SELECT",
  ]

  table {
    database_name = aws_glue_catalog_database.silver_datavault.name
    wildcard      = true
  }
}

resource "aws_s3_object" "cold_script" {
  bucket = var.artifacts_bucket
  key    = "${local.script_prefix}/cold_datavault.py"
  source = var.cold_job_source
  etag   = filemd5(var.cold_job_source)

  tags = merge(var.tags, { Component = "glue-silver-cold" })
}

resource "aws_s3_object" "hot_script" {
  bucket = var.artifacts_bucket
  key    = "${local.script_prefix}/hot_datavault_microbatch.py"
  source = var.hot_job_source
  etag   = filemd5(var.hot_job_source)

  tags = merge(var.tags, { Component = "glue-silver-hot" })
}

resource "aws_s3_object" "runtime" {
  bucket = var.artifacts_bucket
  key    = "${local.script_prefix}/runtime.zip"
  source = data.archive_file.runtime.output_path
  etag   = data.archive_file.runtime.output_md5

  tags = merge(var.tags, { Component = "glue-silver-runtime" })
}

resource "aws_glue_job" "cold_datavault" {
  name                   = "${var.prefix}-silver-cold-datavault"
  description            = "Batch: datasets Olist da raw fria -> Data Vault Iceberg na silver"
  role_arn               = var.role_arn
  glue_version           = var.glue_version
  worker_type            = var.worker_type
  number_of_workers      = var.number_of_workers
  security_configuration = aws_glue_security_configuration.silver.name
  timeout                = 60

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    script_location = "s3://${var.artifacts_bucket}/${aws_s3_object.cold_script.key}"
    python_version  = "3"
  }

  default_arguments = merge(local.common_default_arguments, {
    "--datasets" = var.cold_datasets
  })

  tags = merge(var.tags, { Layer = "silver", Model = "datavault", Runtime = "iceberg" })
}

resource "aws_glue_job" "hot_datavault_microbatch" {
  name                   = "${var.prefix}-silver-hot-datavault"
  description            = "Microbatch: eventos de pedido da raw quente -> Data Vault Iceberg na silver"
  role_arn               = var.role_arn
  glue_version           = var.glue_version
  worker_type            = var.worker_type
  number_of_workers      = var.number_of_workers
  security_configuration = aws_glue_security_configuration.silver.name
  timeout                = 30

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    script_location = "s3://${var.artifacts_bucket}/${aws_s3_object.hot_script.key}"
    python_version  = "3"
  }

  default_arguments = local.common_default_arguments

  tags = merge(var.tags, { Layer = "silver", Model = "datavault", Runtime = "iceberg" })
}

data "aws_iam_policy_document" "eventbridge_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge_glue" {
  name               = "${var.prefix}-eventbridge-glue-silver"
  description        = "Permite ao EventBridge iniciar os jobs Glue da silver"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume.json

  tags = var.tags
}

data "aws_iam_policy_document" "eventbridge_start_glue" {
  statement {
    sid     = "StartSilverGlueJobs"
    actions = ["glue:StartJobRun"]
    resources = [
      aws_glue_job.cold_datavault.arn,
      aws_glue_job.hot_datavault_microbatch.arn,
    ]
  }
}

resource "aws_iam_role_policy" "eventbridge_start_glue" {
  name   = "start-silver-glue-jobs"
  role   = aws_iam_role.eventbridge_glue.id
  policy = data.aws_iam_policy_document.eventbridge_start_glue.json
}

# Uma EventBridge *Rule* não sabe disparar um job Glue: a lista de targets
# nativos tem Glue *workflow*, não job — apontar o ARN do job faz o PutTargets
# devolver "Provided Arn is not in correct format". Quem chama StartJobRun na
# agenda é o EventBridge *Scheduler*, pelo target universal do SDK.
#
# Sem retry: os jobs rodam com max_concurrent_runs = 1, então uma nova tentativa
# em cima de uma execução em andamento só produziria ConcurrentRunsExceeded. O
# próximo tick da agenda é a recuperação natural.
#
# CKV_AWS_297 (CMK na agenda): a CMK só cifra o `input` do target, que aqui é o
# nome do job — não há dado sensível a proteger, e o resto (agenda, ARN, estado)
# a AWS cifra de qualquer forma com chave gerenciada. Em troca, a CMK exigiria
# kms:GenerateDataKey/Decrypt/DescribeKey na identidade que CRIA a agenda (a role
# do CI) e kms:Decrypt na execution role — o Scheduler não usa grants. Custo de
# acoplamento alto para proteger uma string pública.
resource "aws_scheduler_schedule" "cold_job" {
  #checkov:skip=CKV_AWS_297: input do target e o nome do job; sem dado sensivel
  name        = "${var.prefix}-silver-cold-datavault"
  description = "Agenda do job Glue cold raw -> silver Data Vault"
  group_name  = "default"

  schedule_expression = var.cold_schedule_expression

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.eventbridge_glue.arn
    input    = jsonencode({ JobName = aws_glue_job.cold_datavault.name })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

resource "aws_scheduler_schedule" "hot_job" {
  #checkov:skip=CKV_AWS_297: input do target e o nome do job; sem dado sensivel
  name        = "${var.prefix}-silver-hot-datavault"
  description = "Agenda do job Glue hot raw -> silver Data Vault"
  group_name  = "default"

  schedule_expression = var.hot_schedule_expression

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.eventbridge_glue.arn
    input    = jsonencode({ JobName = aws_glue_job.hot_datavault_microbatch.name })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

# ---- Alerta: job Glue FAILED/TIMEOUT -> SNS (agendado falhando nao pode ficar mudo) ----
resource "aws_sns_topic" "job_failures" {
  name              = "${var.prefix}-silver-glue-failures"
  kms_master_key_id = aws_kms_key.glue_security.arn

  tags = var.tags
}

data "aws_iam_policy_document" "sns_publish" {
  statement {
    sid       = "AllowEventBridgePublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.job_failures.arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_sns_topic_policy" "job_failures" {
  arn    = aws_sns_topic.job_failures.arn
  policy = data.aws_iam_policy_document.sns_publish.json
}

resource "aws_cloudwatch_event_rule" "job_failures" {
  name        = "${var.prefix}-silver-glue-failures"
  description = "Notifica falha ou timeout dos jobs Glue da silver"
  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      jobName = [
        aws_glue_job.cold_datavault.name,
        aws_glue_job.hot_datavault_microbatch.name,
      ]
      state = ["FAILED", "TIMEOUT", "ERROR"]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "job_failures" {
  rule = aws_cloudwatch_event_rule.job_failures.name
  arn  = aws_sns_topic.job_failures.arn
}

resource "aws_sns_topic_subscription" "job_failures_email" {
  count = var.alert_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.job_failures.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

