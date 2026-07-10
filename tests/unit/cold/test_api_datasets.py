"""Testes dos endpoints por tabela (keyset por PK + cache-aside)."""
import pytest
from fastapi.testclient import TestClient

from src.cold.api_orders.api.v1.endpoints import (
    customers,
    geolocation,
    order_items,
    order_payments,
    order_reviews,
    product_category_name_translation,
    products,
    sellers,
)
from src.cold.api_orders.core.configs import get_settings
from src.cold.api_orders.core.deps import get_connection
from src.cold.api_orders.main import create_app


SPECS = (
    customers.SPEC,
    sellers.SPEC,
    products.SPEC,
    geolocation.SPEC,
    product_category_name_translation.SPEC,
    order_items.SPEC,
    order_payments.SPEC,
    order_reviews.SPEC,
)


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


def _customer_row(customer_id='c1'):
    return {
        'customer_id': customer_id,
        'customer_unique_id': 'u1',
        'customer_zip_code_prefix': '01310',
        'customer_city': 'sao paulo',
        'customer_state': 'SP',
    }


@pytest.fixture()
def api(monkeypatch):
    """App com conexão fake; TTL do cache controlável por teste."""
    get_settings.cache_clear()

    def factory(rows=(), cache_ttl=None):
        if cache_ttl is not None:
            monkeypatch.setenv('CACHE_TTL_SECONDS', str(cache_ttl))
            get_settings.cache_clear()
        app = create_app()
        conn = FakeConnection(list(rows))

        async def override():
            yield conn

        app.dependency_overrides[get_connection] = override
        return TestClient(app), conn

    yield factory
    get_settings.cache_clear()


@pytest.mark.parametrize('spec', SPECS, ids=lambda spec: spec.name)
def test_every_dataset_responds_empty_page(api, spec):
    client, _ = api()
    response = client.get(f'/v1/{spec.name}')
    assert response.status_code == 200
    assert response.json() == {'items': [], 'next_cursor': None}


def test_openapi_has_one_endpoint_per_rds_table(api):
    client, _ = api()
    paths = client.get('/openapi.json').json()['paths']
    expected = {'/v1/orders', *(f'/v1/{spec.name}' for spec in SPECS)}
    assert expected.issubset(paths)
    for spec in SPECS:
        operation = paths[f'/v1/{spec.name}']['get']
        assert operation['operationId'] == f'list_{spec.name}'
        assert operation['tags'] == [spec.name]


def test_cursor_comes_even_on_partial_page(api):
    """Diferente de /v1/orders: com itens, sempre há cursor para retomar."""
    client, _ = api(rows=[_customer_row()])
    payload = client.get('/v1/customers').json()
    assert len(payload['items']) == 1
    assert payload['next_cursor'] == ['c1']


def test_first_page_queries_without_cursor(api):
    client, conn = api()
    client.get('/v1/customers')
    sql, params = conn.queries[0]
    assert 'WHERE' not in sql
    assert params == {'page_size': 500}


def test_composite_cursor_is_echoed_with_casts(api):
    client, conn = api()
    client.get('/v1/order_items', params={'after': ['o1', '2'], 'page_size': 10})
    sql, params = conn.queries[0]
    assert '::integer' in sql
    assert params == {'page_size': 10, 'key0': 'o1', 'key1': '2'}


def test_cursor_with_wrong_arity_is_rejected(api):
    client, conn = api()
    response = client.get('/v1/order_items', params={'after': ['o1']})
    assert response.status_code == 422
    assert conn.queries == []


def test_page_size_above_max_is_rejected(api):
    client, _ = api()
    response = client.get('/v1/customers', params={'page_size': 1001})
    assert response.status_code == 422



def test_new_app_starts_with_empty_cache(api):
    client_a, _ = api(rows=[_customer_row('a')])
    assert client_a.get('/v1/customers').json()['items'][0]['customer_id'] == 'a'
    client_b, _ = api(rows=[_customer_row('b')])
    assert client_b.get('/v1/customers').json()['items'][0]['customer_id'] == 'b'



def test_cache_hit_skips_database(api):
    client, conn = api(rows=[_customer_row()])
    first = client.get('/v1/customers').json()
    second = client.get('/v1/customers').json()
    assert first == second
    assert len(conn.queries) == 1


def test_cache_key_distinguishes_query_string(api):
    client, conn = api()
    client.get('/v1/customers')
    client.get('/v1/customers', params={'page_size': 10})
    assert len(conn.queries) == 2


def test_cache_disabled_with_zero_ttl(api):
    client, conn = api(rows=[_customer_row()], cache_ttl=0)
    client.get('/v1/customers')
    client.get('/v1/customers')
    assert len(conn.queries) == 2


def test_table_routes_require_token_when_configured(api, monkeypatch):
    monkeypatch.setenv('API_TOKEN', 's3gr3d0')
    get_settings.cache_clear()
    client, _ = api()
    assert client.get('/v1/customers').status_code == 401
    ok = client.get('/v1/customers', headers={'x-api-token': 's3gr3d0'})
    assert ok.status_code == 200







