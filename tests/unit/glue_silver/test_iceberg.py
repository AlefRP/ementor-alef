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
    linhas_unicas_por_chave,
    nome_completo_da_tabela,
    novas_linhas_de_satellite,
    registrar_erro,
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


class SessaoFalsa:
    """Dublê da sessão: registra os SQLs e devolve a 'tabela atual' fixa."""

    def __init__(self, tabela_atual=None):
        self.sqls = []
        self._tabela_atual = tabela_atual

    def sql(self, texto):
        self.sqls.append(texto)

    def table(self, _nome):
        return self._tabela_atual


class EscritaFalsa:
    """Dublê do writeTo(...): conta os appends."""

    def __init__(self):
        self.appends = 0

    def append(self):
        self.appends += 1


class DataFrameFalso:
    """Dublê de DataFrame para as estratégias de merge (sem Spark real)."""

    def __init__(self, sessao, linhas=1):
        self.sparkSession = sessao
        self._linhas = linhas
        self.escrita = EscritaFalsa()
        self.view = None
        self.checkpoints = 0

    def dropDuplicates(self, _chaves):
        return self

    def localCheckpoint(self):
        self.checkpoints += 1
        return self

    def count(self):
        return self._linhas

    def createOrReplaceTempView(self, nome):
        self.view = nome

    def writeTo(self, _nome):
        return self.escrita


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


def test_registrar_erro_emite_json_no_nivel_error(caplog):
    # Arrange
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        # Act
        registrar_erro(event='dataset_failed', dataset='geolocation', error='boom')

    # Assert — falha de dataset sai como ERROR (INFO some no driver do Glue)
    assert caplog.records[-1].levelno == logging.ERROR
    assert json.loads(caplog.records[-1].message)['event'] == 'dataset_failed'


def test_logger_do_runtime_tem_handler_proprio():
    # Arrange / Act — o handler é anexado no import do módulo
    handlers = iceberg.logger.handlers

    # Assert — sem handler explícito o Glue descarta INFO (lastResort é WARNING+)
    assert handlers
    assert iceberg.logger.level == logging.INFO


def test_linhas_unicas_por_chave_mantem_uma_linha_deterministica(spark):
    # Arrange — chave duplicada com atributos diferentes entre os lotes
    df = spark.createDataFrame(
        [('k1', 'b'), ('k1', 'a'), ('k2', 'c')],
        'chave string, atributo string',
    )

    # Act
    unicas = linhas_unicas_por_chave(df, ['chave'])

    # Assert — uma linha por chave e escolha estável (menor valor na ordenação)
    resultado = {r['chave']: r['atributo'] for r in unicas.collect()}
    assert resultado == {'k1': 'a', 'k2': 'c'}


def _ultimo_log(caplog) -> dict:
    """Decodifica o último registro JSON emitido pelo logger do runtime."""
    return json.loads(caplog.records[-1].message)


def test_merge_somente_insere_executa_merge_e_loga_linhas(monkeypatch, caplog):
    # Arrange — hubs/links: MERGE insert-only sobre o stage deduplicado
    monkeypatch.setattr(iceberg, 'garantir_tabela', lambda df, db, table: None)
    sessao = SessaoFalsa()
    df = DataFrameFalso(sessao, linhas=3)

    # Act
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        iceberg.merge_somente_insere(df, 'db', 'hub_x', ['x_hk'])

    # Assert
    assert 'WHEN NOT MATCHED THEN INSERT *' in sessao.sqls[0]
    assert 'UPDATE SET' not in sessao.sqls[0]  # insert-only: nunca atualiza
    assert _ultimo_log(caplog) == {
        'event': 'vault_write',
        'table': 'hub_x',
        'staged_rows': 3,
    }


def test_merge_atualiza_ou_insere_executa_upsert_e_loga_linhas(monkeypatch, caplog):
    # Arrange — references: upsert (estado corrente, sem histórico)
    monkeypatch.setattr(iceberg, 'garantir_tabela', lambda df, db, table: None)
    monkeypatch.setattr(iceberg, 'linhas_unicas_por_chave', lambda df, keys: df)
    sessao = SessaoFalsa()
    df = DataFrameFalso(sessao, linhas=2)

    # Act
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        iceberg.merge_atualiza_ou_insere(df, 'db', 'ref_x', ['k'])

    # Assert — upsert emitido e stage materializado (plano determinístico)
    assert 'WHEN MATCHED THEN UPDATE SET *' in sessao.sqls[0]
    assert df.checkpoints == 1
    assert _ultimo_log(caplog) == {
        'event': 'vault_write',
        'table': 'ref_x',
        'staged_rows': 2,
    }


def test_merge_somente_insere_materializa_tabela_vazia_sem_merge(monkeypatch, caplog):
    # Arrange — raw vazia (0 linhas): a gold precisa da tabela existir mesmo assim
    garantidas = []
    monkeypatch.setattr(
        iceberg, 'garantir_tabela', lambda df, db, table: garantidas.append(table)
    )
    sessao = SessaoFalsa()
    df = DataFrameFalso(sessao, linhas=0)

    # Act
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        iceberg.merge_somente_insere(df, 'db', 'hub_x', ['x_hk'])

    # Assert — tabela garantida, nenhum MERGE, e o log registra 0 linhas
    assert garantidas == ['hub_x']
    assert sessao.sqls == []
    assert _ultimo_log(caplog) == {
        'event': 'vault_write',
        'table': 'hub_x',
        'staged_rows': 0,
    }


def test_merge_atualiza_ou_insere_materializa_tabela_vazia_sem_upsert(
    monkeypatch, caplog
):
    # Arrange — raw vazia (0 linhas): a gold precisa da tabela existir mesmo assim
    garantidas = []
    monkeypatch.setattr(
        iceberg, 'garantir_tabela', lambda df, db, table: garantidas.append(table)
    )
    monkeypatch.setattr(iceberg, 'linhas_unicas_por_chave', lambda df, keys: df)
    sessao = SessaoFalsa()
    df = DataFrameFalso(sessao, linhas=0)

    # Act
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        iceberg.merge_atualiza_ou_insere(df, 'db', 'ref_x', ['k'])

    # Assert — tabela garantida, nenhum upsert, e o log registra 0 linhas
    assert garantidas == ['ref_x']
    assert sessao.sqls == []
    assert _ultimo_log(caplog) == {
        'event': 'vault_write',
        'table': 'ref_x',
        'staged_rows': 0,
    }


def test_merge_de_satellite_anexa_novas_versoes_e_loga_linhas(monkeypatch, caplog):
    # Arrange — satellite: só as linhas com hashdiff novo entram (append)
    monkeypatch.setattr(iceberg, 'garantir_tabela', lambda df, db, table: None)
    sessao = SessaoFalsa(tabela_atual='tabela_atual')
    novas = DataFrameFalso(sessao, linhas=2)
    monkeypatch.setattr(
        iceberg, 'novas_linhas_de_satellite', lambda stage, atual, hk: novas
    )
    df = DataFrameFalso(sessao, linhas=5)

    # Act
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        iceberg.merge_de_satellite(df, 'db', 'sat_x', 'x_hk')

    # Assert
    assert novas.escrita.appends == 1
    assert _ultimo_log(caplog) == {
        'event': 'vault_write',
        'table': 'sat_x',
        'appended_rows': 2,
    }


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
