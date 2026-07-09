"""Simulação dos eventos de pedido da camada quente (SQS).

Reusa o vocabulário de ``simulation/olist.py`` (categorias, UFs, tipos de
pagamento) para que os eventos publicados na fila fiquem no mesmo domínio das
tabelas do RDS — condição para o ETL unir as camadas quente e fria.

Vai empacotado no zip do producer (``make hot-producer-bundle``).
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime

from faker import Faker

from .olist import CUSTOMER_STATES, PAYMENT_TYPES, PRODUCT_CATEGORIES

# Estados de um pedido no fluxo de eventos (o RDS guarda o estado final;
# aqui cada transição vira uma mensagem).
EVENT_ORDER_STATUSES = ('created', 'approved', 'invoiced', 'shipped', 'delivered')

# SystemRandom: sem estado global compartilhado entre invocações warm da Lambda.
# Diferente de olist.py, aqui não há promessa de reprodutibilidade.
_RNG = random.SystemRandom()
_FAKE = Faker('pt_BR')


def new_event(moment: datetime) -> dict:
    """Evento de pedido no formato do data product da camada quente."""
    return {
        'event_id': str(uuid.uuid4()),
        'event_type': f'order_{_RNG.choice(EVENT_ORDER_STATUSES)}',
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
            'product_category_name': _RNG.choice(list(PRODUCT_CATEGORIES)),
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
