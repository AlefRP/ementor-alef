# Camada GOLD — o consumo analítico do lakehouse.
#
# A gold NÃO copia dados: são views do Athena sobre a silver (Iceberg/Data
# Vault). O DV é ótimo para carregar e auditar, e péssimo para consultar — a
# gold é a camada que devolve o modelo dimensional que o negócio entende
# (dim_/fact_), sem duplicar um byte nem exigir um job novo.
#
# O DDL das views vive versionado em src/{cold,hot}/athena_gold/*.sql e é
# aplicado por scripts/athena/apply_views.py (CREATE OR REPLACE VIEW, idempotente).
# Terraform cria aqui o que é INFRA — workgroup e database; a definição das
# views é código, e código não mora no state.

resource "aws_glue_catalog_database" "gold" {
  name        = var.gold_database_name
  description = "Camada gold: views dimensionais sobre a silver Data Vault."

  tags = var.tags
}

# Workgroup dedicado: isola o resultado das queries, força a configuração
# (enforce = o cliente não sobrescreve o bucket de saída) e publica métricas no
# CloudWatch. O corte por bytes escaneados é o freio de custo do lab — Athena
# cobra por dado lido, e uma query sem filtro em Iceberg é um cheque em branco.
resource "aws_athena_workgroup" "gold" {
  name        = "${var.prefix}-gold"
  description = "Consumo analitico da camada gold (views sobre a silver)"
  state       = "ENABLED"

  # Teardown do lab: as queries do consumer deixam histórico no workgroup, e o
  # DeleteWorkGroup falha com "is not empty" sem RecursiveDeleteOption. Igual aos
  # buckets, o provider lê este flag do STATE ao deletar — o tf-force-arm o grava
  # antes do destroy (passar -var no destroy não teria efeito).
  force_destroy = var.force_destroy

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_cutoff

    result_configuration {
      # Resultados no bucket de artefatos (já versionado, cifrado e com Block
      # Public Access); um bucket a mais só para isso não pagaria o custo de
      # existir no teardown.
      output_location = "s3://${var.artifacts_bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  tags = var.tags
}
