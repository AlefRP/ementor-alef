"""Testes dos entrypoints dos jobs Glue silver (cold e hot).

O ``awsglue`` só existe dentro do Glue; aqui os módulos entram como stubs em
``sys.modules`` e os colaboradores do ``main()`` viram dublês — o que se
testa é a ORQUESTRAÇÃO: isolamento de falha por dataset (cold), o log
estruturado de conclusão e o commit do job.
Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
JOB_FRIO = RAIZ / 'src' / 'cold' / 'glue_silver' / 'job.py'
JOB_QUENTE = RAIZ / 'src' / 'hot' / 'glue_silver_microbatch' / 'job.py'


class ContextoGlueFalso:
    """Dublê do GlueContext: só expõe a spark_session."""

    def __init__(self, _sc):
        self.spark_session = 'spark-falsa'


class JobGlueFalso:
    """Dublê do Job do Glue: registra init e commit."""

    ultimo = None

    def __init__(self, _glue):
        self.commits = 0
        JobGlueFalso.ultimo = self

    def init(self, _nome, _args):
        pass

    def commit(self):
        self.commits += 1


@pytest.fixture()
def carregar_job(monkeypatch):
    """Fábrica que importa um job.py com o awsglue stubado em sys.modules."""
    stubs = {
        'awsglue': types.ModuleType('awsglue'),
        'awsglue.context': types.ModuleType('awsglue.context'),
        'awsglue.job': types.ModuleType('awsglue.job'),
        'awsglue.utils': types.ModuleType('awsglue.utils'),
    }
    stubs['awsglue.context'].GlueContext = ContextoGlueFalso
    stubs['awsglue.job'].Job = JobGlueFalso
    stubs['awsglue.utils'].getResolvedOptions = lambda argv, params: {}
    for nome, modulo in stubs.items():
        monkeypatch.setitem(sys.modules, nome, modulo)

    def _carregar(caminho: Path, nome: str):
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, nome, modulo)
        spec.loader.exec_module(modulo)
        return modulo

    return _carregar


def _preparar_main(monkeypatch, modulo, args: dict) -> None:
    """Substitui a infraestrutura do main() por dublês inofensivos."""
    monkeypatch.setattr(modulo, 'SparkContext', lambda: 'sc-falso')
    monkeypatch.setattr(modulo, 'argumentos_do_job', lambda: args)
    monkeypatch.setattr(modulo, 'configurar_iceberg', lambda spark, bucket: None)
    monkeypatch.setattr(modulo, 'garantir_database', lambda spark, db: None)


def _eventos_logados(caplog) -> list[dict]:
    return [json.loads(registro.message) for registro in caplog.records]


def test_argumentos_do_job_frio_declara_o_contrato_do_glue(monkeypatch, carregar_job):
    # Arrange — captura os parâmetros pedidos ao getResolvedOptions
    modulo = carregar_job(JOB_FRIO, 'job_frio_args')
    monkeypatch.setattr(
        modulo, 'getResolvedOptions', lambda argv, params: {'params': params}
    )

    # Act
    resultado = modulo.argumentos_do_job()

    # Assert — o contrato de --args do Terraform precisa bater com este
    assert set(resultado['params']) == {
        'JOB_NAME',
        'raw_bucket',
        'silver_bucket',
        'silver_database',
        'datasets',
    }


def test_argumentos_do_job_quente_declara_o_contrato_do_glue(monkeypatch, carregar_job):
    # Arrange
    modulo = carregar_job(JOB_QUENTE, 'job_quente_args')
    monkeypatch.setattr(
        modulo, 'getResolvedOptions', lambda argv, params: {'params': params}
    )

    # Act
    resultado = modulo.argumentos_do_job()

    # Assert — a quente processa o lote inteiro: não há seleção de datasets
    assert set(resultado['params']) == {
        'JOB_NAME',
        'raw_bucket',
        'silver_bucket',
        'silver_database',
    }


def test_processar_dataset_encadeia_leitura_modelagem_e_escrita(
    monkeypatch, carregar_job
):
    # Arrange — colaboradores viram dublês; a spec e o caminho são reais
    modulo = carregar_job(JOB_FRIO, 'job_frio_pipeline')
    leituras = {}

    def ler(_spark, caminho, dataset, _schema, _prefixo):
        leituras[dataset] = caminho
        return 'df_da_raw'

    monkeypatch.setattr(modulo, 'ler_arquivos_de_lote_json', ler)
    monkeypatch.setattr(
        modulo, 'montar_frames_do_vault', lambda df, vault: ['frame_a', 'frame_b']
    )
    escritos = []
    monkeypatch.setattr(
        modulo,
        'escrever_frame_do_vault',
        lambda frame, db: escritos.append((frame, db)),
    )

    # Act
    modulo.processar_dataset('spark-falsa', 'orders', 'bucket-raw', 'db')

    # Assert — leu do caminho frio do dataset e escreveu todos os frames
    assert 'bucket-raw' in leituras['orders']
    assert escritos == [('frame_a', 'db'), ('frame_b', 'db')]


def test_main_do_job_frio_isola_falha_por_dataset(monkeypatch, carregar_job, caplog):
    # Arrange — um dataset bom e um ruim: o ruim não pode derrubar o bom
    modulo = carregar_job(JOB_FRIO, 'job_frio')
    args = {
        'JOB_NAME': 'job',
        'raw_bucket': 'raw',
        'silver_bucket': 'silver',
        'silver_database': 'db',
        'datasets': 'all',
    }
    _preparar_main(monkeypatch, modulo, args)
    monkeypatch.setattr(
        modulo, 'datasets_selecionados', lambda _sel: ['ds_ok', 'ds_ruim']
    )

    def processar(_spark, dataset, _bucket, _db):
        if dataset == 'ds_ruim':
            raise ValueError('lote inválido')

    monkeypatch.setattr(modulo, 'processar_dataset', processar)

    # Act — o job processa os dois e só falha no FIM (para o alerta disparar)
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        with pytest.raises(RuntimeError, match='ds_ruim'):
            modulo.main()

    # Assert — done para o bom, failed para o ruim, e o commit aconteceu
    eventos = _eventos_logados(caplog)
    assert {'event': 'dataset_done', 'dataset': 'ds_ok'} in eventos
    assert any(
        e['event'] == 'dataset_failed' and e['dataset'] == 'ds_ruim' for e in eventos
    )
    assert JobGlueFalso.ultimo.commits == 1


def test_main_do_job_quente_processa_microbatch_e_commita(
    monkeypatch, carregar_job, caplog
):
    # Arrange — pipeline de eventos vira dublê; o main só orquestra
    modulo = carregar_job(JOB_QUENTE, 'job_quente')
    args = {
        'JOB_NAME': 'job',
        'raw_bucket': 'raw',
        'silver_bucket': 'silver',
        'silver_database': 'db',
    }
    _preparar_main(monkeypatch, modulo, args)
    monkeypatch.setattr(
        modulo, 'ler_arquivos_de_evento_json', lambda *a, **kw: 'eventos'
    )
    monkeypatch.setattr(modulo, 'achatar_eventos', lambda eventos: eventos)
    escritos = []
    monkeypatch.setattr(
        modulo, 'montar_frames_do_vault', lambda df, vault: ['frame_1', 'frame_2']
    )
    monkeypatch.setattr(
        modulo, 'escrever_frame_do_vault', lambda frame, db: escritos.append(frame)
    )

    # Act
    with caplog.at_level(logging.INFO, logger='glue_silver'):
        modulo.main()

    # Assert — todos os frames escritos, log de conclusão e commit
    assert escritos == ['frame_1', 'frame_2']
    assert {'event': 'microbatch_done'} in _eventos_logados(caplog)
    assert JobGlueFalso.ultimo.commits == 1
