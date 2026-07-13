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


def _cliente_s3():
    """Client S3 reaproveitado entre invocações warm."""
    global _S3
    if _S3 is None:
        _S3 = boto3.client('s3')
    return _S3


def _configuracao() -> dict:
    """Lê a configuração do ambiente a cada invocação (testável)."""
    return {
        'raw_bucket': os.environ['RAW_BUCKET'],
        'dataset': os.environ.get('DATASET', 'events'),
    }


def _chave_raw(dataset: str, id_mensagem: str, momento: datetime) -> str:
    """Chave particionada por data de processamento, única por mensagem."""
    return (
        f'{dataset}/year={momento:%Y}/month={momento:%m}/day={momento:%d}/'
        f'{id_mensagem}.json'
    )


def handler(event, context):
    """Persiste cada mensagem do lote; reporta só as que falharam."""
    configuracao = _configuracao()
    momento = datetime.now(timezone.utc)
    falhas = []
    gravados = 0
    for registro in event.get('Records', []):
        id_mensagem = registro['messageId']
        try:
            corpo = json.loads(registro['body'])
            _cliente_s3().put_object(
                Bucket=configuracao['raw_bucket'],
                Key=_chave_raw(configuracao['dataset'], id_mensagem, momento),
                Body=json.dumps(corpo).encode('utf-8'),
            )
            gravados += 1
        except Exception:
            # Loga e segue: a mensagem volta para a fila via batch failure
            # (retry) e cai na DLQ quando esgotar o redrive — nada se perde.
            logger.exception(
                json.dumps({'event': 'record_error', 'message_id': id_mensagem})
            )
            falhas.append({'itemIdentifier': id_mensagem})
    logger.info(
        json.dumps(
            {
                'event': 'ingest_ok',
                'dataset': configuracao['dataset'],
                'stored': gravados,
                'failed': len(falhas),
            }
        )
    )
    return {'batchItemFailures': falhas}
