"""Testes dos leitores da raw: particionamento, metadados e parsing JSON.

Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

import json
from datetime import date

from pyspark.sql.types import StringType, StructField, StructType

from raw import (
    anexar_metadados_da_raw,
    caminho_frio,
    caminho_quente,
    ler_arquivos_de_evento_json,
    ler_arquivos_de_lote_json,
)

SCHEMA_DE_CLIENTE = StructType(
    [
        StructField('customer_id', StringType(), False),
        StructField('customer_unique_id', StringType(), False),
    ]
)


def test_caminhos_da_raw_sao_particionados_por_data():
    # Arrange / Act
    frio = caminho_frio('bkt', 'orders')
    quente = caminho_quente('bkt')

    # Assert
    assert frio == 's3://bkt/orders/year=*/month=*/day=*/*.json'
    assert quente == 's3://bkt/events/year=*/month=*/day=*/*.json'


def test_anexar_metadados_da_raw_extrai_data_da_particao(spark):
    # Arrange
    df = spark.createDataFrame(
        [('s3://bkt/customers/year=2026/month=07/day=10/lote.json',)], ['raw_file']
    )

    # Act
    linha = anexar_metadados_da_raw(df, 'customers', 'raw.olist').first()

    # Assert
    assert (linha.raw_year, linha.raw_month, linha.raw_day) == ('2026', '07', '10')
    assert linha.raw_partition_date == date(2026, 7, 10)
    assert linha.record_source == 'raw.olist.customers'
    assert linha.load_dts is not None


def test_ler_arquivos_de_lote_json_explode_o_lote(spark, tmp_path):
    # Arrange — um lote JSON no layout year=/month=/day= da raw fria
    particao = tmp_path / 'customers' / 'year=2026' / 'month=07' / 'day=10'
    particao.mkdir(parents=True)
    lote = [
        {'customer_id': 'c1', 'customer_unique_id': 'u1'},
        {'customer_id': 'c2', 'customer_unique_id': 'u2'},
    ]
    (particao / 'lote.json').write_text(json.dumps(lote), encoding='utf-8')
    caminho = (tmp_path / 'customers').as_posix() + '/year=*/month=*/day=*/*.json'

    # Act
    df = ler_arquivos_de_lote_json(
        spark, caminho, 'customers', SCHEMA_DE_CLIENTE, 'raw.olist'
    )

    # Assert
    linhas = df.collect()
    assert {linha.customer_id for linha in linhas} == {'c1', 'c2'}
    assert all(linha.raw_partition_date == date(2026, 7, 10) for linha in linhas)


def test_ler_arquivos_de_evento_json_um_evento_por_arquivo(spark, tmp_path):
    # Arrange — um evento JSON no layout year=/month=/day= da raw quente
    particao = tmp_path / 'events' / 'year=2026' / 'month=07' / 'day=10'
    particao.mkdir(parents=True)
    (particao / 'e1.json').write_text(json.dumps({'event_id': 'e1'}), encoding='utf-8')
    schema = StructType([StructField('event_id', StringType(), False)])
    caminho = (tmp_path / 'events').as_posix() + '/year=*/month=*/day=*/*.json'

    # Act
    linha = ler_arquivos_de_evento_json(
        spark, caminho, 'events', schema, 'raw.hot'
    ).first()

    # Assert
    assert linha.event_id == 'e1'
    assert linha.record_source == 'raw.hot.events'
    assert linha.raw_partition_date == date(2026, 7, 10)
