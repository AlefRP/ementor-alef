"""Testes do mapeamento Data Vault dos eventos quentes.

Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

from datetime import datetime

from pyspark.sql import functions as F

from cold_specs import DATASETS
from hot_specs import EVENT_SCHEMA, EVENT_VAULT, achatar_eventos
from raw import anexar_metadados_da_raw


def test_quente_e_frio_compartilham_hubs_de_integracao():
    # Arrange
    hubs_do_frio = {
        hub.table: hub for spec in DATASETS.values() for hub in spec.vault.hubs
    }
    hubs_do_quente = {hub.table: hub for hub in EVENT_VAULT.hubs}

    # Act
    compartilhados = set(hubs_do_frio) & set(hubs_do_quente)

    # Assert — mesmo hub = mesma chave de negócio (integração DV 2.0)
    assert {'hub_order', 'hub_customer'} <= compartilhados
    for tabela in compartilhados:
        assert hubs_do_frio[tabela].business_key == hubs_do_quente[tabela].business_key
        assert hubs_do_frio[tabela].key_cols == hubs_do_quente[tabela].key_cols


def test_pagamento_e_contexto_do_link_event_order():
    # Arrange
    satellites = {sat.table: sat for sat in EVENT_VAULT.satellites}

    # Act
    pagamento = satellites['sat_hot_payment_snapshot']

    # Assert — pagamento descreve o relacionamento evento<->pedido
    assert pagamento.parent_hk == 'link_event_order_hk'
    assert pagamento.parent_key_cols == ['event_id', 'order_id']


def test_achatar_eventos_achata_o_payload(spark):
    # Arrange — um evento aninhado como chega do SQS/raw
    evento = {
        'event_id': 'e1',
        'event_type': 'order_created',
        'event_timestamp': datetime(2026, 7, 10, 12, 0),
        'customer': {
            'customer_unique_id': 'u1',
            'customer_name': 'Ana',
            'customer_city': 'sao paulo',
            'customer_state': 'SP',
            'customer_zip_code_prefix': '01310',
        },
        'order': {
            'order_id': 'o1',
            'product_category_name': 'pet_shop',
            'product_name': 'racao',
            'items_count': 1,
            'price': 10.0,
            'freight_value': 2.0,
        },
        'payment': {'payment_type': 'credit_card', 'payment_installments': 2},
    }
    df = spark.createDataFrame([evento], EVENT_SCHEMA).withColumn(
        'raw_file', F.lit('s3://bkt/events/year=2026/month=07/day=10/e1.json')
    )
    df = anexar_metadados_da_raw(df, 'events', 'raw.hot')

    # Act
    achatado = achatar_eventos(df).first()

    # Assert
    assert achatado.event_id == 'e1'
    assert achatado.order_id == 'o1'
    assert achatado.customer_unique_id == 'u1'
    assert achatado.payment_type == 'credit_card'
    assert achatado.record_source == 'raw.hot.events'
