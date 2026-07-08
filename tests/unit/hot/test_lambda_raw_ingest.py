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
def ingest_env(monkeypatch):
    """Ambiente mínimo da Lambda com client S3 zerado por teste."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('RAW_BUCKET', BUCKET)
    ingest._S3 = None
    yield
    ingest._S3 = None


def _sqs_event(*records):
    return {'Records': list(records)}


def _record(message_id, body):
    return {'messageId': message_id, 'body': body}


def _bucket_keys():
    result = boto3.client('s3').list_objects_v2(Bucket=BUCKET)
    return [item['Key'] for item in result.get('Contents', [])]


@mock_aws
def test_handler_stores_one_object_per_message(ingest_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    event = _sqs_event(
        _record('msg-1', json.dumps({'event_id': 'a'})),
        _record('msg-2', json.dumps({'event_id': 'b'})),
    )

    result = ingest.handler(event, None)

    assert result == {'batchItemFailures': []}
    keys = _bucket_keys()
    assert len(keys) == 2
    for key in keys:
        assert re.match(r'^events/year=\d{4}/month=\d{2}/day=\d{2}/', key)
    assert any('msg-1.json' in key for key in keys)


@mock_aws
def test_handler_reports_only_failed_messages(ingest_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    event = _sqs_event(
        _record('ok-1', json.dumps({'event_id': 'a'})),
        _record('ruim-1', 'nao-e-json{'),
    )

    result = ingest.handler(event, None)

    assert result == {'batchItemFailures': [{'itemIdentifier': 'ruim-1'}]}
    assert len(_bucket_keys()) == 1


@mock_aws
def test_handler_is_idempotent_for_reprocessed_message(ingest_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    record = _record('repetida', json.dumps({'event_id': 'a'}))

    ingest.handler(_sqs_event(record), None)
    ingest.handler(_sqs_event(record), None)

    assert len(_bucket_keys()) == 1


@mock_aws
def test_handler_marks_all_failed_on_s3_error(ingest_env):
    # Bucket não existe: cada mensagem falha e volta para a fila (sem raise,
    # para não descartar o lote inteiro sem reporte granular).
    event = _sqs_event(
        _record('m1', json.dumps({'a': 1})),
        _record('m2', json.dumps({'b': 2})),
    )
    result = ingest.handler(event, None)
    identifiers = {f['itemIdentifier'] for f in result['batchItemFailures']}
    assert identifiers == {'m1', 'm2'}


def test_raw_key_partitions_by_processing_date():
    moment = datetime(2026, 7, 8, 15, 30, 0, tzinfo=timezone.utc)
    key = ingest._raw_key('events', 'abc-123', moment)
    assert key == 'events/year=2026/month=07/day=08/abc-123.json'
