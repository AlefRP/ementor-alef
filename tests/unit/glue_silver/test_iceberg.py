"""Testes das estratégias de escrita Data Vault (sem catálogo Iceberg real).

Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

import json
import logging

import pytest

import iceberg
from iceberg import (
    CATALOG,
    condicao_do_merge,
    configurar_iceberg,
    escrever_frame_do_vault,
    nome_completo_da_tabela,
    novas_linhas_de_satellite,
    registrar_log,
)
from vault import VaultFrame


class FakeConf:
    """Dublê do spark.conf: só registra o que foi configurado."""

    def __init__(self):
        self.valores = {}

    def set(self, chave, valor):
        self.valores[chave] = valor


class FakeSpark:
    """Dublê mínimo de SparkSession para testar configuração."""

    def __init__(self):
        self.conf = FakeConf()


def _df_de_satellite(spark, linhas):
    """Monta um DataFrame com as colunas mínimas de um satellite."""
    return spark.createDataFrame(
        linhas, 'x_hk string, state string, hashdiff string, load_dts string'
    )


def test_nome_completo_da_tabela_usa_catalogo_glue():
    # Arrange / Act
    nome = nome_completo_da_tabela('db', 'hub_x')

    # Assert
    assert nome == f'{CATALOG}.db.hub_x'


def test_condicao_do_merge_combina_todas_as_chaves():
    # Arrange / Act
    condicao = condicao_do_merge(['a', 'b'])

    # Assert
    assert condicao == 't.a = s.a AND t.b = s.b'


def test_configurar_iceberg_aponta_warehouse_para_o_bucket():
    # Arrange
    spark_falso = FakeSpark()

    # Act
    configurar_iceberg(spark_falso, 'meu-bucket')

    # Assert
    warehouse = spark_falso.conf.valores[f'spark.sql.catalog.{CATALOG}.warehouse']
    assert warehouse == 's3://meu-bucket/warehouse/'


def test_registrar_log_emite_json_estruturado(caplog):
    # Arrange
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        # Act
        registrar_log(event='vault_write', table='hub_x', staged_rows=3)

    # Assert
    assert json.loads(caplog.records[0].message) == {
        'event': 'vault_write',
        'table': 'hub_x',
        'staged_rows': 3,
    }


def test_novas_linhas_de_satellite_insere_reativacao_de_valor_antigo(spark):
    # Arrange — hd_a existe na HISTÓRIA, mas o MAIS RECENTE é hd_b
    historico = _df_de_satellite(
        spark,
        [('k1', 'SP', 'hd_a', '2026-01-01'), ('k1', 'RJ', 'hd_b', '2026-01-02')],
    )
    stage = _df_de_satellite(spark, [('k1', 'SP', 'hd_a', '2026-01-03')])

    # Act
    novas = novas_linhas_de_satellite(stage, historico, 'x_hk')

    # Assert — o valor voltou (A -> B -> A): a reativação deve entrar
    assert novas.count() == 1


def test_novas_linhas_de_satellite_ignora_versao_igual_a_ultima(spark):
    # Arrange
    historico = _df_de_satellite(spark, [('k1', 'RJ', 'hd_b', '2026-01-02')])
    stage = _df_de_satellite(spark, [('k1', 'RJ', 'hd_b', '2026-01-03')])

    # Act
    novas = novas_linhas_de_satellite(stage, historico, 'x_hk')

    # Assert
    assert novas.count() == 0


def test_novas_linhas_de_satellite_insere_chave_inedita(spark):
    # Arrange
    historico = _df_de_satellite(spark, [])
    stage = _df_de_satellite(spark, [('k9', 'SP', 'hd_z', '2026-01-03')])

    # Act
    novas = novas_linhas_de_satellite(stage, historico, 'x_hk')

    # Assert
    assert novas.count() == 1


def test_escrever_frame_do_vault_despacha_pela_estrategia(monkeypatch):
    # Arrange — substitui as estratégias por registradores de chamada
    chamadas = []
    monkeypatch.setattr(
        iceberg,
        'merge_somente_insere',
        lambda df, db, table, keys: chamadas.append(('insere', table)),
    )
    monkeypatch.setattr(
        iceberg,
        'merge_de_satellite',
        lambda df, db, table, hk: chamadas.append(('satellite', table, hk)),
    )
    monkeypatch.setattr(
        iceberg,
        'merge_atualiza_ou_insere',
        lambda df, db, table, keys: chamadas.append(('upsert', table)),
    )

    # Act
    escrever_frame_do_vault(VaultFrame('hub', 'hub_x', None, ['x_hk']), 'db')
    escrever_frame_do_vault(VaultFrame('link', 'link_x', None, ['l_hk']), 'db')
    escrever_frame_do_vault(VaultFrame('satellite', 'sat_x', None, ['x_hk']), 'db')
    escrever_frame_do_vault(VaultFrame('reference', 'ref_x', None, ['k']), 'db')

    # Assert
    assert chamadas == [
        ('insere', 'hub_x'),
        ('insere', 'link_x'),
        ('satellite', 'sat_x', 'x_hk'),
        ('upsert', 'ref_x'),
    ]


def test_escrever_frame_do_vault_rejeita_tipo_desconhecido():
    # Arrange
    frame_invalido = VaultFrame('pit', 'pit_x', None, [])

    # Act / Assert
    with pytest.raises(ValueError):
        escrever_frame_do_vault(frame_invalido, 'db')
