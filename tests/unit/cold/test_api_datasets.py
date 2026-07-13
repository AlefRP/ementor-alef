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
from src.cold.api_orders.core.configs import obter_configuracoes
from src.cold.api_orders.core.deps import obter_conexao
from src.cold.api_orders.main import criar_app

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


class CursorFalso:
    def __init__(self, linhas):
        self._linhas = linhas

    async def fetchall(self):
        return self._linhas


class ConexaoFalsa:
    def __init__(self, linhas):
        self.linhas = linhas
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append((sql, params))
        return CursorFalso(self.linhas)


def _linha_de_cliente(customer_id='c1'):
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
    obter_configuracoes.cache_clear()

    def fabrica(linhas=(), cache_ttl=None):
        if cache_ttl is not None:
            monkeypatch.setenv('CACHE_TTL_SECONDS', str(cache_ttl))
            obter_configuracoes.cache_clear()
        app = criar_app()
        conexao = ConexaoFalsa(list(linhas))

        async def override():
            yield conexao

        app.dependency_overrides[obter_conexao] = override
        return TestClient(app), conexao

    yield fabrica
    obter_configuracoes.cache_clear()


@pytest.mark.parametrize('spec', SPECS, ids=lambda spec: spec.name)
def test_todo_dataset_responde_pagina_vazia(api, spec):
    # Arrange
    client, _ = api()

    # Act
    resposta = client.get(f'/v1/{spec.name}')

    # Assert
    assert resposta.status_code == 200
    assert resposta.json() == {'items': [], 'next_cursor': None}


def test_openapi_tem_um_endpoint_por_tabela_do_rds(api):
    client, _ = api()

    paths = client.get('/openapi.json').json()['paths']

    esperados = {'/v1/orders', *(f'/v1/{spec.name}' for spec in SPECS)}
    assert esperados.issubset(paths)
    for spec in SPECS:
        operacao = paths[f'/v1/{spec.name}']['get']
        assert operacao['operationId'] == f'list_{spec.name}'
        assert operacao['tags'] == [spec.name]


def test_cursor_vem_mesmo_em_pagina_parcial(api):
    # Diferente de /v1/orders: com itens, sempre há cursor para retomar.
    client, _ = api(linhas=[_linha_de_cliente()])

    payload = client.get('/v1/customers').json()

    assert len(payload['items']) == 1
    assert payload['next_cursor'] == ['c1']


def test_primeira_pagina_consulta_sem_cursor(api):
    client, conexao = api()

    client.get('/v1/customers')

    sql, params = conexao.queries[0]
    assert 'WHERE' not in sql
    assert params == {'page_size': 500}


def test_cursor_composto_e_ecoado_com_casts(api):
    # Arrange — order_items tem PK composta (order_id, order_item_id)
    client, conexao = api()

    # Act
    client.get('/v1/order_items', params={'after': ['o1', '2'], 'page_size': 10})

    # Assert — cada valor do cursor vira um placeholder tipado
    sql, params = conexao.queries[0]
    assert '::integer' in sql
    assert params == {'page_size': 10, 'key0': 'o1', 'key1': '2'}


def test_cursor_com_aridade_errada_e_rejeitado(api):
    client, conexao = api()

    resposta = client.get('/v1/order_items', params={'after': ['o1']})

    assert resposta.status_code == 422
    assert conexao.queries == []


def test_page_size_acima_do_max_e_rejeitado(api):
    client, _ = api()

    resposta = client.get('/v1/customers', params={'page_size': 1001})

    assert resposta.status_code == 422


def test_app_novo_comeca_com_cache_vazio(api):
    client_a, _ = api(linhas=[_linha_de_cliente('a')])
    assert client_a.get('/v1/customers').json()['items'][0]['customer_id'] == 'a'

    client_b, _ = api(linhas=[_linha_de_cliente('b')])
    assert client_b.get('/v1/customers').json()['items'][0]['customer_id'] == 'b'


def test_cache_hit_nao_toca_o_banco(api):
    # Arrange
    client, conexao = api(linhas=[_linha_de_cliente()])

    # Act — mesma URL duas vezes
    primeira = client.get('/v1/customers').json()
    segunda = client.get('/v1/customers').json()

    # Assert — resposta idêntica e só UMA query no banco
    assert primeira == segunda
    assert len(conexao.queries) == 1


def test_chave_de_cache_distingue_query_string(api):
    client, conexao = api()

    client.get('/v1/customers')
    client.get('/v1/customers', params={'page_size': 10})

    assert len(conexao.queries) == 2


def test_cache_desligado_com_ttl_zero(api):
    client, conexao = api(linhas=[_linha_de_cliente()], cache_ttl=0)

    client.get('/v1/customers')
    client.get('/v1/customers')

    assert len(conexao.queries) == 2


def test_rotas_de_tabela_exigem_token_quando_configurado(api, monkeypatch):
    monkeypatch.setenv('API_TOKEN', 's3gr3d0')
    obter_configuracoes.cache_clear()
    client, _ = api()

    assert client.get('/v1/customers').status_code == 401
    ok = client.get('/v1/customers', headers={'x-api-token': 's3gr3d0'})
    assert ok.status_code == 200
