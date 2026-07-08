---
name: aws-lambda-ingestion
description: >-
  Use ao escrever funções AWS Lambda de ingestão do lakehouse — consumir uma API
  (camada fria, gatilho EventBridge) ou eventos SQS (camada quente) e persistir
  na camada raw do S3 particionada por year/month/day, com boto3, logging
  estruturado e tratamento de erros. Acione em "Lambda", "ingestão", "EventBridge",
  "consumir SQS", "gravar na raw".
---

# AWS Lambda — ingestão para a camada raw (S3)

Duas variantes no lakehouse: **fria** (EventBridge agenda a Lambda que puxa a API)
e **quente** (SQS aciona a Lambda por evento). Ambas escrevem na `raw` particionada.

## Contrato do handler (convenção do repo)

```python
import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
RAW_BUCKET = os.environ["RAW_BUCKET"]


def handler(event, context):
    """Ingere um lote e grava em s3://<raw>/<dataset>/year=/month=/day=/."""
    try:
        records = _extract(event)
        key = _raw_key(dataset="pedidos")
        s3.put_object(
            Bucket=RAW_BUCKET,
            Key=key,
            Body=json.dumps(records).encode("utf-8"),
        )
        logger.info(json.dumps({"event": "ingest_ok", "key": key, "count": len(records)}))
        return {"statusCode": 200, "ingested": len(records)}
    except Exception:
        logger.exception(json.dumps({"event": "ingest_error"}))
        raise  # propaga: aciona retry/DLQ (SQS) e falha visível (EventBridge)


def _raw_key(dataset: str) -> str:
    now = datetime.now(timezone.utc)
    return (
        f"{dataset}/year={now:%Y}/month={now:%m}/day={now:%d}/"
        f"{now:%H%M%S}-{now.microsecond}.json"
    )
```

## Regras (repo)

- **Assinatura padrão** `handler(event, context)`.
- **Particionamento `year/month/day`** no path da raw — sempre.
- **Sem credenciais no código** — usa a role de execução (ver `lakehouse-governance`,
  role `lambda-ingest-*` com `PutObject` só em `raw/*`).
- **Logging estruturado** (JSON via `logger`), nunca `print`.
- **Tratamento de erro**: capture, logue com contexto e **re-lance** para acionar
  retry/DLQ (hot) ou marcar falha (cold). Não engula exceção.
- **Idempotência**: chave inclui timestamp de alta resolução; para exactly-once,
  derive a chave de um id do evento.
- **`boto3`** para AWS. Config de bucket/fila via variáveis de ambiente.

## Variante quente (SQS)

```python
def handler(event, context):
    for record in event["Records"]:           # batch do SQS
        body = json.loads(record["body"])
        # ... processa e grava na raw ...
    # falha parcial: use ReportBatchItemFailures p/ reprocessar só o que falhou
```

## Testes (obrigatório para o gate de cobertura ≥ 90%)

- Padrão `test_<unidade>_<cenario>` em `tests/unit/`.
- Mocke S3/SQS com `moto` ou `unittest.mock`; nunca chame AWS real no unit.
- Cubra: caminho feliz, payload inválido, erro do S3 (garante o `raise`).
- Marque integração com `@pytest.mark.integration`.

## Erros comuns (evite)

- ❌ Path sem partição `year/month/day`.
- ❌ Engolir exceção (`except: pass`) → perde retry/DLQ e mascara falha.
- ❌ Bucket/fila hardcoded no código.
- ❌ `print` em vez de logging estruturado.
- ❌ Não tratar batch parcial do SQS (reprocessa mensagens já OK).

Ver também: `glue-iceberg-job` (consome a raw), `lakehouse-governance` (role da Lambda),
`terraform-aws-module` (provisiona a Lambda/SQS/EventBridge).
