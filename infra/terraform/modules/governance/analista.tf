# Consumo humano do lakehouse: o analista consulta a gold pelo Athena e NUNCA
# toca o S3 dos dados — a leitura passa pelo Lake Formation (GetDataAccess +
# grants SELECT), que vende credencial temporária escopada por tabela. O IAM
# daqui cobre só o "trilho": workgroup, metadados do catálogo e o prefixo de
# resultados das queries. Senha de console é criada fora do Terraform (root),
# para não passar por state nem por histórico de shell.
# (data aws_region/aws_caller_identity vêm de roles.tf/lakeformation.tf.)

locals {
  conta  = data.aws_caller_identity.current.account_id
  regiao = data.aws_region.current.name
  # ARNs construídos (não referência) para o for_each dos grants LF ter
  # chaves conhecidas no plan; a ordem fica garantida pelo depends_on.
  analistas_arns = [
    for nome in var.analistas :
    "arn:aws:iam::${local.conta}:user/${var.prefix}-analista-${nome}"
  ]
}

resource "aws_iam_user" "analista" {
  #checkov:skip=CKV_AWS_273: Identity Center exige AWS Organizations, fora do escopo da conta standalone do lab; o consumo humano e cercado por IAM de trilho + Lake Formation. SSO registrado como evolucao em infra/iam/terraform-user/README.md
  for_each = toset(var.analistas)

  name = "${var.prefix}-analista-${each.value}"
  # Login profile/access keys criados fora do Terraform não travam o destroy.
  force_destroy = true

  tags = var.tags
}

data "aws_iam_policy_document" "analista" {
  statement {
    sid = "AthenaSoNoWorkgroupGold"
    actions = [
      "athena:BatchGetQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetWorkGroup",
      "athena:ListQueryExecutions",
      "athena:StartQueryExecution",
      "athena:StopQueryExecution",
    ]
    resources = [
      "arn:aws:athena:${local.regiao}:${local.conta}:workgroup/${var.gold_workgroup_name}"
    ]
  }

  statement {
    sid = "NavegacaoDoCatalogoNoAthena"
    actions = [
      "athena:GetDataCatalog",
      "athena:GetDatabase",
      "athena:GetTableMetadata",
      "athena:ListDatabases",
      "athena:ListTableMetadata",
    ]
    resources = [
      "arn:aws:athena:${local.regiao}:${local.conta}:datacatalog/AwsDataCatalog"
    ]
  }

  statement {
    sid = "MetadadosGlueDaSilverEDaGold"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:GetTable",
      "glue:GetTables",
      "glue:SearchTables",
    ]
    resources = [
      "arn:aws:glue:${local.regiao}:${local.conta}:catalog",
      "arn:aws:glue:${local.regiao}:${local.conta}:database/${var.silver_database_name}",
      "arn:aws:glue:${local.regiao}:${local.conta}:database/${var.gold_database_name}",
      "arn:aws:glue:${local.regiao}:${local.conta}:table/${var.silver_database_name}/*",
      "arn:aws:glue:${local.regiao}:${local.conta}:table/${var.gold_database_name}/*",
    ]
  }

  # GetDataAccess e os List* de navegação não aceitam recurso específico
  # (limitação documentada da AWS) — o escopo REAL do dado não está aqui:
  # vem dos grants SELECT/DESCRIBE do Lake Formation na silver e na gold.
  statement {
    sid = "LakeFormationVendeAsCredenciais"
    actions = [
      "athena:ListDataCatalogs",
      "athena:ListWorkGroups",
      "lakeformation:GetDataAccess",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "LocalizacaoDoBucketDeResultados"
    actions   = ["s3:GetBucketLocation"]
    resources = [var.artifacts_bucket_arn]
  }

  statement {
    sid       = "ListagemSoDoPrefixoDeResultados"
    actions   = ["s3:ListBucket"]
    resources = [var.artifacts_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["athena-results/*"]
    }
  }

  statement {
    sid = "LeituraEEscritaDosResultados"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${var.artifacts_bucket_arn}/athena-results/*"]
  }
}

resource "aws_iam_policy" "analista" {
  name        = "${var.prefix}-analista-consumo"
  description = "Consumo da gold via Athena + Lake Formation (sem S3 direto nos dados)"
  policy      = data.aws_iam_policy_document.analista.json

  tags = var.tags
}

resource "aws_iam_user_policy_attachment" "analista" {
  #checkov:skip=CKV_AWS_40: os grants do Lake Formation sao por USER (LF nao aceita IAM group como principal); um grupo para 2 analistas seria camada extra carregando uma unica policy. Revisar se a lista crescer
  for_each = aws_iam_user.analista

  user       = each.value.name
  policy_arn = aws_iam_policy.analista.arn
}
