"""Testes da Lambda de ingestão quente (SQS → raw S3)."""
import json
import re
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

from src.hot.lambda_raw_ingest import handler as ingest

BUCKET = 'raw-quente-teste'


@pytest.fixture()
def ambiente_da_lambda(monkeypatch):
    """Ambiente mínimo da Lambda com client S3 zerado por teste."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('RAW_BUCKET', BUCKET)
    ingest._S3 = None
    yield
    ingest._S3 = None


def _evento_sqs(*registros):
    return {'Records': list(registros)}


def _registro(id_mensagem, corpo):
    return {'messageId': id_mensagem, 'body': corpo}


def _chaves_do_bucket():
    resultado = boto3.client('s3').list_objects_v2(Bucket=BUCKET)
    return [item['Key'] for item in resultado.get('Contents', [])]


@mock_aws
def test_handler_grava_um_objeto_por_mensagem(ambiente_da_lambda):
    # Arrange
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    evento = _evento_sqs(
        _registro('msg-1', json.dumps({'event_id': 'a'})),
        _registro('msg-2', json.dumps({'event_id': 'b'})),
    )

    # Act
    resultado = ingest.handler(evento, None)

    # Assert
    assert resultado == {'batchItemFailures': []}
    chaves = _chaves_do_bucket()
    assert len(chaves) == 2
    for chave in chaves:
        assert re.match(r'^events/year=\d{4}/month=\d{2}/day=\d{2}/', chave)
    assert any('msg-1.json' in chave for chave in chaves)


@mock_aws
def test_handler_reporta_so_as_mensagens_com_falha(ambiente_da_lambda):
    # Arrange
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    evento = _evento_sqs(
        _registro('ok-1', json.dumps({'event_id': 'a'})),
        _registro('ruim-1', 'nao-e-json{'),
    )

    # Act
    resultado = ingest.handler(evento, None)

    # Assert
    assert resultado == {'batchItemFailures': [{'itemIdentifier': 'ruim-1'}]}
    assert len(_chaves_do_bucket()) == 1


@mock_aws
def test_handler_e_idempotente_para_mensagem_reprocessada(ambiente_da_lambda):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    registro = _registro('repetida', json.dumps({'event_id': 'a'}))

    ingest.handler(_evento_sqs(registro), None)
    ingest.handler(_evento_sqs(registro), None)

    assert len(_chaves_do_bucket()) == 1


@mock_aws
def test_handler_marca_todas_com_falha_em_erro_s3(ambiente_da_lambda):
    # Bucket não existe: cada mensagem falha e volta para a fila (sem raise,
    # para não descartar o lote inteiro sem reporte granular).
    evento = _evento_sqs(
        _registro('m1', json.dumps({'a': 1})),
        _registro('m2', json.dumps({'b': 2})),
    )

    resultado = ingest.handler(evento, None)

    identificadores = {f['itemIdentifier'] for f in resultado['batchItemFailures']}
    assert identificadores == {'m1', 'm2'}


def test_chave_raw_particiona_por_data_de_processamento():
    momento = datetime(2026, 7, 8, 15, 30, 0, tzinfo=timezone.utc)

    chave = ingest._chave_raw('events', 'abc-123', momento)

    assert chave == 'events/year=2026/month=07/day=08/abc-123.json'
