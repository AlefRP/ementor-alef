"""Lambda de ingestão quente: consome eventos do SQS e grava na raw (S3).

Acionada pelo event source mapping com ``ReportBatchItemFailures``: apenas
as mensagens que falham voltam para a fila (e, esgotado o redrive, caem na
DLQ) — as demais são confirmadas. Um objeto por mensagem, com chave derivada
do ``messageId`` (reprocessamento sobrescreve o mesmo objeto: idempotente).
Roda na VPC; o S3 é alcançado pelo gateway endpoint. Módulo autocontido.
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_S3 = None


def _s3_client():
    """Client S3 reaproveitado entre invocações warm."""
    global _S3
    if _S3 is None:
        _S3 = boto3.client('s3')
    return _S3


def _config() -> dict:
    """Lê a configuração do ambiente a cada invocação (testável)."""
    return {
        'raw_bucket': os.environ['RAW_BUCKET'],
        'dataset': os.environ.get('DATASET', 'events'),
    }


def _raw_key(dataset: str, message_id: str, moment: datetime) -> str:
    """Chave particionada por data de processamento, única por mensagem."""
    return (
        f'{dataset}/year={moment:%Y}/month={moment:%m}/day={moment:%d}/'
        f'{message_id}.json'
    )


def handler(event, context):
    """Persiste cada mensagem do lote; reporta só as que falharam."""
    config = _config()
    moment = datetime.now(timezone.utc)
    failures = []
    stored = 0
    for record in event.get('Records', []):
        message_id = record['messageId']
        try:
            body = json.loads(record['body'])
            _s3_client().put_object(
                Bucket=config['raw_bucket'],
                Key=_raw_key(config['dataset'], message_id, moment),
                Body=json.dumps(body).encode('utf-8'),
            )
            stored += 1
        except Exception:
            # Loga e segue: a mensagem volta para a fila via batch failure
            # (retry) e cai na DLQ quando esgotar o redrive — nada se perde.
            logger.exception(
                json.dumps({'event': 'record_error', 'message_id': message_id})
            )
            failures.append({'itemIdentifier': message_id})
    logger.info(
        json.dumps(
            {
                'event': 'ingest_ok',
                'dataset': config['dataset'],
                'stored': stored,
                'failed': len(failures),
            }
        )
    )
    return {'batchItemFailures': failures}
