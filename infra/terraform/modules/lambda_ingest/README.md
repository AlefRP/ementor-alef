# lambda_ingest — Lambda de ingestão fria (EventBridge → API → raw)

Empacota `src/cold/lambda_ingest/handler.py` (autocontido, stdlib + boto3) e
provisiona a função **dentro da VPC** (subnets privadas): a API é chamada
pelo DNS privado da EC2 e o S3 pelo gateway endpoint — tráfego 100% privado.

Decisões:

- `reserved_concurrent_executions = 1`: uma execução por vez preserva a
  semântica do marker (`_markers/<dataset>.json`, cursor keyset retomável).
- `arm64` (Graviton) + 256 MB: menor custo por ms para um batch pequeno.
- X-Ray ativo; logs com retenção de 365 dias.
- Sem DLQ: batch idempotente — a execução seguinte retoma do marker
  (justificado no skip do checkov CKV_AWS_116).

Role de execução vem do módulo `governance` (PutObject na raw, GetObject só
em `_markers/*`, ENIs de VPC via managed policy).
