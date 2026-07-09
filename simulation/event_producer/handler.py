"""Lambda produtora de eventos sintéticos de pedidos (camada quente).

Agendada via EventBridge e FORA da VPC de propósito: o SQS não tem gateway
endpoint gratuito, e daqui a fila é alcançada pelo endpoint público da AWS
com TLS + IAM (a policy da fila nega conexões não-TLS).

A geração dos eventos vive em ``simulation/events.py`` (simulação, empacotada
no zip junto com o Faker — ver ``make hot-producer-bundle``); aqui fica só a
orquestração: montar lotes de até 10 e publicar com ``send_message_batch``.
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3

from ..events import new_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SQS_BATCH_MAX = 10

_SQS = None


def _sqs_client():
    """Client SQS reaproveitado entre invocações warm."""
    global _SQS
    if _SQS is None:
        _SQS = boto3.client('sqs')
    return _SQS


def _config() -> dict:
    """Lê a configuração do ambiente a cada invocação (testável)."""
    return {
        'queue_url': os.environ['QUEUE_URL'],
        'events_per_run': int(os.environ.get('EVENTS_PER_RUN', '60')),
    }


def handler(event, context):
    """Gera N eventos e publica na fila em lotes de até 10."""
    config = _config()
    published = 0
    try:
        moment = datetime.now(timezone.utc)
        events = [new_event(moment) for _ in range(config['events_per_run'])]
        for start in range(0, len(events), SQS_BATCH_MAX):
            batch = events[start : start + SQS_BATCH_MAX]
            entries = [
                {'Id': str(index), 'MessageBody': json.dumps(item)}
                for index, item in enumerate(batch)
            ]
            response = _sqs_client().send_message_batch(
                QueueUrl=config['queue_url'], Entries=entries
            )
            rejected = response.get('Failed', [])
            if rejected:
                raise RuntimeError(f'{len(rejected)} mensagens rejeitadas pelo SQS')
            published += len(batch)
        logger.info(json.dumps({'event': 'produce_ok', 'published': published}))
        return {'statusCode': 200, 'published': published}
    except Exception:
        logger.exception(json.dumps({'event': 'produce_error', 'published': published}))
        raise
