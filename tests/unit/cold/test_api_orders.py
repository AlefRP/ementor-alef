"""Testes da API fria (data product Olist)."""
import asyncio
from datetime import datetime
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool

from src.cold.api_orders.core import database
from src.cold.api_orders.core.configs import Settings, get_settings
from src.cold.api_orders.core.database import (
    IamAuthPool,
    create_pool,
    iam_auth_token,
    resolve_password,
)
from src.cold.api_orders.core.deps import get_connection
from src.cold.api_orders.main import create_app


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append((sql, params))
        return FakeCursor(self.rows)


def _order_row(order_id='o1', purchased=datetime(2018, 5, 1, 12, 0, 0)):
    return {
        'order_id': order_id,
        'customer_id': 'c1',
        'order_status': 'delivered',
        'order_purchase_timestamp': purchased,
        'order_approved_at': None,
        'order_delivered_carrier_date': None,
        'order_delivered_customer_date': None,
        'order_estimated_delivery_date': None,
    }


@pytest.fixture()
def api(monkeypatch):
    """Fábrica de app com conexão fake injetada por dependency override."""
    get_settings.cache_clear()

    def factory(rows=(), token=''):
        if token:
            monkeypatch.setenv('API_TOKEN', token)
            get_settings.cache_clear()
        app = create_app()
        conn = FakeConnection(list(rows))

        async def override():
            yield conn

        app.dependency_overrides[get_connection] = override
        return TestClient(app), conn

    yield factory
    get_settings.cache_clear()


def test_health_returns_ok(api):
    client, _ = api()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_response_includes_correlation_id_header(api):
    client, _ = api()
    response = client.get('/health')
    assert response.headers['x-correlation-id']


def test_incoming_correlation_id_is_preserved(api):
    client, _ = api()
    response = client.get('/health', headers={'x-correlation-id': 'abc-123'})
    assert response.headers['x-correlation-id'] == 'abc-123'


def test_list_orders_without_cursor_on_partial_page(api):
    client, _ = api(rows=[_order_row()])
    response = client.get('/v1/orders')
    payload = response.json()
    assert response.status_code == 200
    assert len(payload['items']) == 1
    assert payload['next_cursor'] is None


def test_list_orders_returns_next_cursor_on_full_page(api):
    rows = [
        _order_row('o1', datetime(2018, 5, 1, 10, 0, 0)),
        _order_row('o2', datetime(2018, 5, 2, 10, 0, 0)),
    ]
    client, _ = api(rows=rows)
    response = client.get('/v1/orders', params={'page_size': 2})
    cursor = response.json()['next_cursor']
    assert cursor['after_id'] == 'o2'
    assert cursor['purchased_after'] == '2018-05-02T10:00:00'


def test_list_orders_sends_keyset_params_to_query(api):
    client, conn = api()
    client.get(
        '/v1/orders',
        params={
            'purchased_after': '2018-01-01T00:00:00',
            'after_id': 'o9',
            'page_size': 10,
        },
    )
    _, params = conn.queries[0]
    assert params['purchased_after'] == datetime(2018, 1, 1)
    assert params['after_id'] == 'o9'
    assert params['page_size'] == 10


def test_list_orders_rejects_page_size_above_max(api):
    client, _ = api()
    response = client.get('/v1/orders', params={'page_size': 1001})
    assert response.status_code == 422


def test_list_orders_rejects_invalid_purchased_after(api):
    client, _ = api()
    response = client.get('/v1/orders', params={'purchased_after': 'ontem'})
    assert response.status_code == 422


def test_v1_requires_token_when_configured(api):
    client, _ = api(token='s3gr3d0')
    assert client.get('/v1/orders').status_code == 401
    ok = client.get('/v1/orders', headers={'x-api-token': 's3gr3d0'})
    assert ok.status_code == 200


def test_health_does_not_require_token(api):
    client, _ = api(token='s3gr3d0')
    assert client.get('/health').status_code == 200


def test_unhandled_error_returns_500_with_correlation_id(api):
    client, _ = api()
    app = client.app

    async def explode():
        raise RuntimeError('boom')
        yield  # pragma: no cover

    app.dependency_overrides[get_connection] = explode
    response = client.get('/v1/orders')
    assert response.status_code == 500
    assert response.json()['correlation_id']


def test_lifespan_opens_and_closes_pool(api, monkeypatch):
    monkeypatch.setenv('POOL_MIN_SIZE', '0')
    monkeypatch.setenv('PGPASSWORD', 'x')
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert app.state.pool is not None


def test_resolve_password_prefers_environment():
    settings = Settings(PGPASSWORD='direta', SECRET_ARN='arn:ignorado')
    assert resolve_password(settings) == 'direta'


def test_resolve_password_reads_secrets_manager():
    settings = Settings(PGPASSWORD='', SECRET_ARN='arn:aws:sm:secret')
    fake = mock.Mock()
    fake.get_secret_value.return_value = {'SecretString': '{"password": "do-secret"}'}
    with mock.patch('boto3.client', return_value=fake):
        assert resolve_password(settings) == 'do-secret'
    fake.get_secret_value.assert_called_once_with(SecretId='arn:aws:sm:secret')


def test_resolve_password_empty_without_sources():
    settings = Settings(PGPASSWORD='', SECRET_ARN='')
    assert resolve_password(settings) == ''


def test_create_pool_is_closed_and_sized_from_settings():
    settings = Settings(PGPASSWORD='x', POOL_MIN_SIZE=0, POOL_MAX_SIZE=3)
    pool = create_pool(settings)
    assert pool.min_size == 0
    assert pool.max_size == 3
    assert pool.closed


def test_iam_auth_token_signs_locally():
    settings = Settings(PGHOST='db.interno', PGPORT=5432, PGUSER='api_reader')
    fake = mock.Mock()
    fake.generate_db_auth_token.return_value = 'token-iam'
    with mock.patch('boto3.client', return_value=fake):
        assert iam_auth_token(settings) == 'token-iam'
    fake.generate_db_auth_token.assert_called_once_with(
        DBHostname='db.interno', Port=5432, DBUsername='api_reader'
    )


def test_create_pool_iam_mode_uses_tls_and_iam_pool():
    settings = Settings(DB_AUTH='iam', POOL_MIN_SIZE=0)
    pool = create_pool(settings)
    assert isinstance(pool, IamAuthPool)
    assert 'sslmode=require' in pool.conninfo


def test_iam_pool_refreshes_token_on_each_connection(monkeypatch):
    settings = Settings(DB_AUTH='iam', POOL_MIN_SIZE=0)
    pool = create_pool(settings)
    monkeypatch.setattr(database, 'iam_auth_token', lambda _: 'tok-novo')

    async def fake_connect(self, timeout=None):
        return 'conexao'

    monkeypatch.setattr(AsyncConnectionPool, '_connect', fake_connect)
    assert asyncio.run(pool._connect()) == 'conexao'
    assert pool.kwargs['password'] == 'tok-novo'
