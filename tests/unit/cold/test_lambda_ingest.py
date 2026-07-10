"""Testes da Lambda de ingestão fria (API → raw S3)."""
import json
import re
from datetime import datetime, timezone
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.cold.lambda_ingest import handler as ingest

BUCKET = 'ementor-raw-test'


@pytest.fixture()
def lambda_env(monkeypatch):
    """Ambiente mínimo da Lambda com client S3 zerado por teste."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('API_BASE_URL', 'http://api.lakehouse.internal:8000')
    monkeypatch.setenv('RAW_BUCKET', BUCKET)
    monkeypatch.setenv('PAGE_SIZE', '2')
    ingest._S3 = None
    yield
    ingest._S3 = None


def _order(order_id, purchased):
    return {
        'order_id': order_id,
        'order_status': 'delivered',
        'order_purchase_timestamp': purchased,
    }


def _bucket_keys():
    client = boto3.client('s3')
    result = client.list_objects_v2(Bucket=BUCKET)
    return [item['Key'] for item in result.get('Contents', [])]


@mock_aws
def test_handler_ingests_pages_and_updates_marker(lambda_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    pages = [
        {
            'items': [
                _order('o1', '2018-05-01T10:00:00'),
                _order('o2', '2018-05-02T10:00:00'),
            ]
        },
        {'items': [_order('o3', '2018-05-03T10:00:00')]},
    ]
    with mock.patch.object(ingest, '_fetch_page', side_effect=pages):
        result = ingest.handler({}, None)

    assert result == {'statusCode': 200, 'ingested': 3, 'pages': 2}
    keys = _bucket_keys()
    data_keys = [key for key in keys if key.startswith('orders/')]
    assert len(data_keys) == 2
    for key in data_keys:
        assert re.match(r'^orders/year=\d{4}/month=\d{2}/day=\d{2}/', key)
    marker = json.loads(
        boto3.client('s3')
        .get_object(Bucket=BUCKET, Key='_markers/orders.json')['Body']
        .read()
    )
    assert marker == {
        'purchased_after': '2018-05-03T10:00:00',
        'after_id': 'o3',
    }


@mock_aws
def test_handler_resumes_from_saved_marker(lambda_env):
    client = boto3.client('s3')
    client.create_bucket(Bucket=BUCKET)
    saved = {'purchased_after': '2018-06-01T00:00:00', 'after_id': 'o42'}
    client.put_object(
        Bucket=BUCKET,
        Key='_markers/orders.json',
        Body=json.dumps(saved).encode(),
    )
    with mock.patch.object(ingest, '_fetch_page', return_value={'items': []}) as fetch:
        ingest.handler({}, None)
    assert fetch.call_args[0][1] == saved


@mock_aws
def test_handler_without_new_data_writes_nothing(lambda_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    with mock.patch.object(ingest, '_fetch_page', return_value={'items': []}):
        result = ingest.handler({}, None)
    assert result == {'statusCode': 200, 'ingested': 0, 'pages': 0}
    assert _bucket_keys() == []


@mock_aws
def test_handler_stops_at_max_pages(lambda_env, monkeypatch):
    monkeypatch.setenv('MAX_PAGES', '1')
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    full_page = {
        'items': [
            _order('o1', '2018-05-01T10:00:00'),
            _order('o2', '2018-05-02T10:00:00'),
        ]
    }
    with mock.patch.object(ingest, '_fetch_page', return_value=full_page) as fetch:
        result = ingest.handler({}, None)
    assert fetch.call_count == 1
    assert result['pages'] == 1


@mock_aws
def test_handler_propagates_api_error(lambda_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    with mock.patch.object(ingest, '_fetch_page', side_effect=RuntimeError('API fora')):
        with pytest.raises(RuntimeError):
            ingest.handler({}, None)
    assert _bucket_keys() == []


@mock_aws
def test_handler_propagates_s3_error(lambda_env):
    # Bucket não existe: o put_object da primeira página deve falhar alto.
    page = {'items': [_order('o1', '2018-05-01T10:00:00')]}
    with mock.patch.object(ingest, '_fetch_page', return_value=page):
        with pytest.raises(ClientError):
            ingest.handler({}, None)


def test_fetch_page_builds_url_with_cursor_and_token(lambda_env, monkeypatch):
    monkeypatch.setenv('API_TOKEN', 'tok3n')
    captured = {}

    class FakeResponse:
        def read(self):
            return json.dumps({'items': []}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None, context=None):
        captured['url'] = request.full_url
        captured['token'] = request.get_header('X-api-token')
        return FakeResponse()

    monkeypatch.setattr(ingest.urllib.request, 'urlopen', fake_urlopen)
    marker = {'purchased_after': '2018-01-01T00:00:00', 'after_id': 'o7'}
    body = ingest._fetch_page(ingest._config(), marker)

    assert body == {'items': []}
    assert 'purchased_after=2018-01-01T00%3A00%3A00' in captured['url']
    assert 'after_id=o7' in captured['url']
    assert 'page_size=2' in captured['url']
    assert captured['token'] == 'tok3n'


def test_fetch_page_rejects_unsupported_scheme(lambda_env, monkeypatch):
    monkeypatch.setenv('API_BASE_URL', 'ftp://interno')
    marker = {'purchased_after': ingest.KEYSET_START, 'after_id': ''}
    with pytest.raises(ValueError):
        ingest._fetch_page(ingest._config(), marker)


def test_raw_key_partitions_by_execution_date():
    moment = datetime(2026, 7, 7, 13, 45, 9, 123456, tzinfo=timezone.utc)
    key = ingest._raw_key('orders', 3, moment)
    assert key == ('orders/year=2026/month=07/day=07/134509-123456-page0003.json')


@mock_aws
def test_handler_pk_mode_ingests_and_stores_opaque_marker(lambda_env):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    pages = [
        {
            'items': [{'customer_id': 'c1'}, {'customer_id': 'c2'}],
            'next_cursor': ['c2'],
        },
        {'items': []},
    ]
    event = {'dataset': 'customers', 'cursor_mode': 'pk'}
    with mock.patch.object(ingest, '_fetch_page', side_effect=pages):
        result = ingest.handler(event, None)

    assert result == {'statusCode': 200, 'ingested': 2, 'pages': 1}
    assert any(key.startswith('customers/year=') for key in _bucket_keys())
    marker = json.loads(
        boto3.client('s3')
        .get_object(Bucket=BUCKET, Key='_markers/customers.json')['Body']
        .read()
    )
    assert marker == {'after': ['c2']}


@mock_aws
def test_handler_pk_mode_resumes_from_saved_marker(lambda_env):
    client = boto3.client('s3')
    client.create_bucket(Bucket=BUCKET)
    saved = {'after': ['c42']}
    client.put_object(
        Bucket=BUCKET,
        Key='_markers/customers.json',
        Body=json.dumps(saved).encode(),
    )
    event = {'dataset': 'customers', 'cursor_mode': 'pk'}
    with mock.patch.object(ingest, '_fetch_page', return_value={'items': []}) as fetch:
        ingest.handler(event, None)
    assert fetch.call_args[0][1] == saved


def test_fetch_page_pk_mode_repeats_after_params(lambda_env, monkeypatch):
    captured = {}

    class FakeResponse:
        def read(self):
            return json.dumps({'items': []}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None, context=None):
        captured['url'] = request.full_url
        return FakeResponse()

    monkeypatch.setattr(ingest.urllib.request, 'urlopen', fake_urlopen)
    config = ingest._config({'dataset': 'order_items', 'cursor_mode': 'pk'})
    body = ingest._fetch_page(config, {'after': ['o1', '2']})

    assert body == {'items': []}
    assert '/v1/order_items?' in captured['url']
    assert 'after=o1&after=2' in captured['url']
    assert 'page_size=2' in captured['url']


def test_config_event_overrides_environment(lambda_env):
    config = ingest._config({'dataset': 'sellers', 'cursor_mode': 'pk', 'page_size': 7})
    assert config['dataset'] == 'sellers'
    assert config['cursor_mode'] == 'pk'
    assert config['page_size'] == 7


def test_advance_marker_pk_keeps_marker_without_cursor(lambda_env):
    """Defensivo: sem next_cursor não há como avançar — mantém o cursor."""
    config = {'cursor_mode': 'pk'}
    marker = {'after': ['x']}
    body = {'items': [{'customer_id': 'c9'}]}
    assert ingest._advance_marker(config, marker, body) == marker
