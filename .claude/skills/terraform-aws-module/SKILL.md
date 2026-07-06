---
name: terraform-aws-module
description: >-
  Use ao criar, alterar ou revisar código Terraform neste repositório
  (infra/terraform/**) — módulos de VPC, subnets, security groups, S3, SQS, RDS,
  IAM ou Lake Formation. Garante que o código passe nos gates da esteira
  (terraform fmt, validate, tflint, checkov) e siga least-privilege, Block Public
  Access e state remoto. Acione em pedidos como "provisionar", "criar módulo
  terraform", "adicionar recurso AWS", "corrigir checkov/tflint".
---

# Terraform AWS — autoria de infraestrutura (lakehouse mentoria)

Fonte de verdade: **AWS Prescriptive Guidance — Terraform AWS Provider Best
Practices** + fluxo *diagnose-first* (Anton Babenko `terraform-skill`). Este repo
usa `terraform >= 1.6` e provider `hashicorp/aws ~> 5.0`.

## Fluxo diagnose-first (siga nesta ordem)

1. **Diagnostique antes de escrever.** Leia o diretório do ambiente alvo
   (`infra/terraform/environments/<env>/`) e os módulos existentes. Nunca duplique
   um recurso já declarado.
2. **Escreva o mínimo necessário.** Um recurso por vez, com `description`/`tags`.
3. **Rode os gates locais** (espelham o CI — ver `.github/workflows/ci.yml`):
   ```bash
   make tf-fmt           # formata
   make tf-validate      # init -backend=false + validate
   make tf-lint          # tflint
   make tf-security      # checkov -d <dir>
   ```
4. **Só então** proponha `make tf-plan TF_ENV=<env>` (isso autentica na AWS via
   STS — trate como integração real, não rode sem necessidade).

## Estrutura de módulos (convenção do repo)

```
infra/terraform/
  environments/<env>/     # composição: providers.tf, versions.tf, main.tf
  modules/<nome>/         # reutilizável: main.tf, variables.tf, outputs.tf, README.md
```
- Ambiente **compõe** módulos; módulos **não** fixam provider/region (herdam do root).
- Nomeie recursos por função, não por serviço: `aws_s3_bucket.raw`, não `bucket1`.
- `variables.tf` com `type` + `description` + `validation` quando fizer sentido.
- `outputs.tf` expõe ARNs/ids que outros módulos consomem.

## Regras não-negociáveis (gates de segurança)

| Regra | Como aplicar |
|---|---|
| **S3 Block Public Access** | `aws_s3_bucket_public_access_block` com os 4 flags `true` em TODO bucket (raw, silver, state). |
| **State remoto seguro** | backend `s3` em bucket dedicado + versionado + criptografado; `dynamodb` ou lockfile para lock. Ver `versions.tf`. |
| **Least privilege IAM** | nunca `Action: "*"` nem `Resource: "*"`. Liste APIs e restrinja a ARNs/prefixos. Ver skill `lakehouse-governance`. |
| **Criptografia** | `server_side_encryption_configuration` (S3), `storage_encrypted = true` (RDS), `kms_master_key_id` (SQS) quando aplicável. |
| **Sem segredos hardcoded** | senhas RDS via `aws_secretsmanager_secret`/variável sensível, nunca literal. |
| **checkov limpo** | resolva os findings; suprima só com `#checkov:skip=CKV_ID: justificativa` documentada. |

## Erros comuns de LLM (checklist — evite)

- ❌ Recriar `provider "aws"` dentro de um módulo (o root já define).
- ❌ Bucket S3 sem `public_access_block` (checkov CKV_AWS_53/54/55/56).
- ❌ Policy IAM com `"s3:*"` — expanda para as ações reais (`s3:GetObject`, `s3:PutObject`, `s3:ListBucket`).
- ❌ RDS `publicly_accessible = true` ou sem `storage_encrypted`.
- ❌ Esquecer `depends_on`/referência entre subnet ↔ SG ↔ RDS (use referências implícitas via atributos).
- ❌ Rodar `terraform apply` — neste repo o apply é manual/rollback; a esteira só faz `plan`.

## DO / DON'T

```hcl
# DO — bucket raw com bloqueio público e criptografia
resource "aws_s3_bucket" "raw" {
  bucket = "${var.prefix}-raw"
  tags   = var.tags
}
resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DON'T — bucket exposto, sem criptografia, ACL pública
resource "aws_s3_bucket" "bad" {
  bucket = "meu-bucket"
  acl    = "public-read"   # nunca
}
```

Ver também: `lakehouse-governance` (Lake Formation + IAM roles), `glue-iceberg-job`,
`aws-lambda-ingestion`.
