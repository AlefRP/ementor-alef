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
  #checkov:skip=CKV_AWS_195: script no bucket privado/versionado; jobs sem segredo em SecurityConfiguration dedicada no lab
  name              = "${var.prefix}-silver-cold-datavault"
  description       = "Batch: datasets Olist da raw fria -> Data Vault Iceberg na silver"
  role_arn          = var.role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = 60

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
  #checkov:skip=CKV_AWS_195: script no bucket privado/versionado; jobs sem segredo em SecurityConfiguration dedicada no lab
  name              = "${var.prefix}-silver-hot-datavault"
  description       = "Microbatch: eventos de pedido da raw quente -> Data Vault Iceberg na silver"
  role_arn          = var.role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = 30

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

resource "aws_cloudwatch_event_rule" "cold_schedule" {
  name                = "${var.prefix}-silver-cold-datavault"
  description         = "Agenda do job Glue cold raw -> silver Data Vault"
  schedule_expression = var.cold_schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "hot_schedule" {
  name                = "${var.prefix}-silver-hot-datavault"
  description         = "Agenda do job Glue hot raw -> silver Data Vault"
  schedule_expression = var.hot_schedule_expression

  tags = var.tags
}

data "aws_iam_policy_document" "eventbridge_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
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

resource "aws_cloudwatch_event_target" "cold_job" {
  rule     = aws_cloudwatch_event_rule.cold_schedule.name
  arn      = aws_glue_job.cold_datavault.arn
  role_arn = aws_iam_role.eventbridge_glue.arn
}

resource "aws_cloudwatch_event_target" "hot_job" {
  rule     = aws_cloudwatch_event_rule.hot_schedule.name
  arn      = aws_glue_job.hot_datavault_microbatch.arn
  role_arn = aws_iam_role.eventbridge_glue.arn
}

# ---- Alerta: job Glue FAILED/TIMEOUT -> SNS (agendado falhando nao pode ficar mudo) ----
resource "aws_sns_topic" "job_failures" {
  #checkov:skip=CKV_AWS_26: topico de alerta operacional sem dado sensivel; CMK dedicada fora do escopo do lab
  name = "${var.prefix}-silver-glue-failures"

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

