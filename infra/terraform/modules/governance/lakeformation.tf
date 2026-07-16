# Critério de aceitação: raw e silver mapeados como "Data Lake Locations" no
# Lake Formation, registrados com uma role de serviço dedicada (não a
# service-linked default, para manter o acesso auditável e com escopo).
data "aws_caller_identity" "current" {}

# Quem aplica o Terraform precisa ser administrador do data lake para poder
# conceder permissões (GrantPermissions). A AWS NÃO aceita root como admin —
# use o IAM user/role dedicado (ex.: terraform).
resource "aws_lakeformation_data_lake_settings" "this" {
  admins = [data.aws_caller_identity.current.arn]

  lifecycle {
    precondition {
      condition     = !endswith(data.aws_caller_identity.current.arn, ":root")
      error_message = "Lake Formation não aceita root como administrador. Rode o apply com o IAM user 'terraform' (aws configure com as access keys dele)."
    }
  }
}

data "aws_iam_policy_document" "lakeformation_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lakeformation.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lakeformation_data_access" {
  name               = "${var.prefix}-lakeformation-data-access"
  description        = "Role de registro dos data lake locations (raw/silver)"
  assume_role_policy = data.aws_iam_policy_document.lakeformation_assume.json

  tags = var.tags
}

# Lake Formation vende credenciais desta role a quem tem permissão de dados;
# por isso ela enxerga os dois buckets — mas somente eles.
data "aws_iam_policy_document" "lakeformation_s3" {
  statement {
    sid = "DataLakeLocations"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.raw_bucket_arn,
      "${var.raw_bucket_arn}/*",
      var.silver_bucket_arn,
      "${var.silver_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "lakeformation_s3" {
  name   = "s3-data-lake-locations"
  role   = aws_iam_role.lakeformation_data_access.id
  policy = data.aws_iam_policy_document.lakeformation_s3.json
}

resource "aws_lakeformation_resource" "raw" {
  arn      = var.raw_bucket_arn
  role_arn = aws_iam_role.lakeformation_data_access.arn
}

resource "aws_lakeformation_resource" "silver" {
  arn      = var.silver_bucket_arn
  role_arn = aws_iam_role.lakeformation_data_access.arn
}

# Glue precisa de DATA_LOCATION_ACCESS para criar tabelas apontando para os
# locations (raw na leitura de catálogo, silver na escrita Iceberg).
resource "aws_lakeformation_permissions" "glue_raw_location" {
  principal   = aws_iam_role.glue_job.arn
  permissions = ["DATA_LOCATION_ACCESS"]

  data_location {
    arn = aws_lakeformation_resource.raw.arn
  }

  depends_on = [aws_lakeformation_data_lake_settings.this]
}

resource "aws_lakeformation_permissions" "glue_silver_location" {
  principal   = aws_iam_role.glue_job.arn
  permissions = ["DATA_LOCATION_ACCESS"]

  data_location {
    arn = aws_lakeformation_resource.silver.arn
  }

  depends_on = [aws_lakeformation_data_lake_settings.this]
}

# Quem CONSULTA o lakehouse (console, consumer via CLI, esteira) não lê nada de
# graça: o admin do data lake tem DESCRIBE implícito, mas SELECT é sempre grant
# explícito — e as tabelas da silver pertencem à role do Glue, que as criou.
# Views do Athena não são "definer": consultar a gold exige SELECT também nas
# tabelas da silver que cada view referencia — por isso o grant nas duas camadas.
locals {
  # Sem lista explícita, o consumo é de quem aplica (o IAM user admin do lab —
  # o mesmo principal do consumer via CLI e da esteira).
  consumidores = (
    length(var.consumer_principal_arns) > 0
    ? var.consumer_principal_arns
    : [data.aws_caller_identity.current.arn]
  )
}

resource "aws_lakeformation_permissions" "consumer_silver_tables" {
  for_each = toset(local.consumidores)

  principal   = each.value
  permissions = ["SELECT", "DESCRIBE"]

  table {
    database_name = var.silver_database_name
    wildcard      = true # todas as tabelas DV, atuais e futuras
  }

  depends_on = [aws_lakeformation_data_lake_settings.this]
}

resource "aws_lakeformation_permissions" "consumer_gold_tables" {
  for_each = toset(local.consumidores)

  principal   = each.value
  permissions = ["SELECT", "DESCRIBE"]

  table {
    database_name = var.gold_database_name
    wildcard      = true # todas as views dimensionais, atuais e futuras
  }

  depends_on = [aws_lakeformation_data_lake_settings.this]
}
