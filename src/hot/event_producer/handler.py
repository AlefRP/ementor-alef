"""Lambda produtora de eventos sintéticos de pedidos (camada quente).

Agendada via EventBridge e FORA da VPC de propósito: o SQS não tem gateway
endpoint gratuito, e daqui a fila é alcançada pelo endpoint público da AWS
com TLS + IAM (a policy da fila nega conexões não-TLS). Gera eventos coerentes
com o domínio Olist usando **Faker** (locale pt_BR) para nomes, cidades e
produtos realistas, e publica em lotes de até 10 mensagens
(``send_message_batch``). O Faker é empacotado no zip (ver make hot-producer-bundle).
"""
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone

import boto3
from faker import Faker

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SQS_BATCH_MAX = 10

# Vocabulário do próprio dataset Olist — mantém os eventos da camada quente
# consistentes com os dados do RDS (mesmo espaço de categorias/UFs), para um
# ETL raw->silver->gold que junta as duas camadas fazer sentido.
ORDER_STATUSES = ('created', 'approved', 'invoiced', 'shipped', 'delivered')
PAYMENT_TYPES = ('credit_card', 'boleto', 'voucher', 'debit_card', 'pix')
PRODUCT_CATEGORIES = (
    'cama_mesa_banho',
    'beleza_saude',
    'esporte_lazer',
    'moveis_decoracao',
    'informatica_acessorios',
    'utilidades_domesticas',
    'relogios_presentes',
    'telefonia',
    'brinquedos',
    'automotivo',
)
CUSTOMER_STATES = ('SP', 'RJ', 'MG', 'RS', 'PR', 'SC', 'BA', 'DF', 'GO', 'ES')

# Faker pt_BR reaproveitado entre invocações warm; SystemRandom para escolhas
# de vocabulário fixo (fonte do SO, sem estado global compartilhado).
_FAKE = Faker('pt_BR')
_RNG = random.SystemRandom()

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


def _new_event(moment: datetime) -> dict:
    """Evento de pedido no formato do data product da camada quente."""
    return {
        'event_id': str(uuid.uuid4()),
        'event_type': f'order_{_RNG.choice(ORDER_STATUSES)}',
        'event_timestamp': moment.isoformat(),
        'customer': {
            'customer_unique_id': uuid.uuid4().hex,
            'customer_name': _FAKE.name(),
            'customer_city': _FAKE.city(),
            'customer_state': _RNG.choice(CUSTOMER_STATES),
            'customer_zip_code_prefix': _FAKE.postcode()[:5],
        },
        'order': {
            'order_id': uuid.uuid4().hex,
            'product_category_name': _RNG.choice(PRODUCT_CATEGORIES),
            'product_name': _FAKE.word().capitalize(),
            'items_count': _RNG.randint(1, 4),
            'price': round(_RNG.uniform(15.0, 800.0), 2),
            'freight_value': round(_RNG.uniform(5.0, 60.0), 2),
        },
        'payment': {
            'payment_type': _RNG.choice(PAYMENT_TYPES),
            'payment_installments': _RNG.randint(1, 10),
        },
    }


def handler(event, context):
    """Gera N eventos e publica na fila em lotes de até 10."""
    config = _config()
    published = 0
    try:
        moment = datetime.now(timezone.utc)
        events = [_new_event(moment) for _ in range(config['events_per_run'])]
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
