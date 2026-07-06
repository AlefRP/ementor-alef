---
name: lakehouse-governance
description: >-
  Use ao configurar governança e permissões do data lake na AWS: registrar
  buckets S3 (raw/silver) como Data Lake Locations no AWS Lake Formation e criar
  roles IAM de execução (Glue, Lambda, EC2) com least-privilege — leitura/escrita
  restrita apenas aos prefixos S3 necessários. Acione em "Lake Formation",
  "registrar bucket", "role de execução", "permissões do datalake", "IAM Glue/Lambda".
---

# Governança do Lakehouse — Lake Formation + IAM least-privilege

Cobre a story de governança (3 pts): buckets raw/silver mapeados como *Data Lake
Locations* e roles de Glue/Lambda/EC2 com o **princípio do menor privilégio**.
Fonte: AWS Prescriptive Guidance (IAM least-privilege) + docs Lake Formation.

## Princípios (comece do zero e adicione)

1. **Comece com policy vazia** e adicione só as ações/recursos comprovadamente usados.
2. **Uma role por serviço/função** (glue-silver, lambda-ingest-cold, lambda-ingest-hot, ec2-api). Nunca uma role "faz-tudo".
3. **Escopo por prefixo S3**, não por bucket inteiro quando possível (`arn:aws:s3:::bucket/raw/*`).
4. **Roles, não users**: credenciais temporárias via `assume_role`, sem access keys de longa duração no código.
5. **Confused-deputy guard**: `Condition` no assume-role policy (`aws:SourceAccount`/`aws:SourceArn`).

## Padrão 1 — Registrar buckets no Lake Formation

```hcl
# Registra o local S3 no Lake Formation usando uma role de serviço dedicada.
resource "aws_lakeformation_resource" "raw" {
  arn      = aws_s3_bucket.raw.arn
  role_arn = aws_iam_role.lakeformation_data_access.arn
}

resource "aws_lakeformation_resource" "silver" {
  arn      = aws_s3_bucket.silver.arn
  role_arn = aws_iam_role.lakeformation_data_access.arn
}

# Concede permissões de dados a um principal (ex.: role do Glue) sobre um local.
resource "aws_lakeformation_permissions" "glue_silver_write" {
  principal   = aws_iam_role.glue_job.arn
  permissions = ["DATA_LOCATION_ACCESS"]
  data_location {
    arn = aws_s3_bucket.silver.arn
  }
}
```

## Padrão 2 — Role de execução com escopo mínimo (Glue)

```hcl
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
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# Lê raw, escreve silver — nada além disso.
data "aws_iam_policy_document" "glue_s3" {
  statement {
    sid       = "ReadRaw"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*"]
  }
  statement {
    sid       = "WriteSilver"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.silver.arn, "${aws_s3_bucket.silver.arn}/*"]
  }
}
resource "aws_iam_role_policy" "glue_s3" {
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.glue_s3.json
}
```

## Matriz de escopo por serviço (least-privilege alvo)

| Role | S3 | Outros | Nunca |
|---|---|---|---|
| `lambda-ingest-cold` | `PutObject` em `raw/*` | logs CloudWatch | ler silver, `s3:*` |
| `lambda-ingest-hot` | `PutObject` em `raw/*` | `sqs:ReceiveMessage/DeleteMessage` na fila | ler silver |
| `glue-silver` | ler `raw/*`, escrever `silver/*` | Lake Formation `DATA_LOCATION_ACCESS`, Glue Catalog | IAM, deletar buckets |
| `ec2-api` | (mínimo) | Secrets Manager da API | acesso amplo a dados |

## Checklist de revisão

- [ ] 4 flags de Block Public Access em raw e silver.
- [ ] Nenhuma policy com `Action:"*"` ou `Resource:"*"`.
- [ ] Cada role restrita a prefixos (`raw/*`, `silver/*`), não bucket inteiro sem necessidade.
- [ ] Assume-role com `Condition` de conta/origem.
- [ ] Buckets raw e silver registrados como `aws_lakeformation_resource`.
- [ ] `checkov` limpo nas policies IAM (CKV_AWS_1/107/108/111...).

Ver também: `terraform-aws-module` (gates e estrutura), `glue-iceberg-job`,
`aws-lambda-ingestion`.
