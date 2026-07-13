"""Testes da API fria (data product Olist)."""
import asyncio
from datetime import datetime
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool

from src.cold.api_orders.core import database
from src.cold.api_orders.core.configs import Settings, obter_configuracoes
from src.cold.api_orders.core.database import (
    IamAuthPool,
    criar_pool,
    gerar_token_iam,
    resolver_senha,
)
from src.cold.api_orders.core.deps import obter_conexao
from src.cold.api_orders.main import criar_app


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


def _linha_de_pedido(order_id='o1', purchased=datetime(2018, 5, 1, 12, 0, 0)):
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
    obter_configuracoes.cache_clear()

    def fabrica(linhas=(), token=''):
        if token:
            monkeypatch.setenv('API_TOKEN', token)
            obter_configuracoes.cache_clear()
        app = criar_app()
        conexao = ConexaoFalsa(list(linhas))

        async def override():
            yield conexao

        app.dependency_overrides[obter_conexao] = override
        return TestClient(app), conexao

    yield fabrica
    obter_configuracoes.cache_clear()


def test_health_retorna_ok(api):
    # Arrange
    client, _ = api()

    # Act
    resposta = client.get('/health')

    # Assert
    assert resposta.status_code == 200
    assert resposta.json() == {'status': 'ok'}


def test_resposta_inclui_header_de_correlation_id(api):
    client, _ = api()

    resposta = client.get('/health')

    assert resposta.headers['x-correlation-id']


def test_correlation_id_recebido_e_preservado(api):
    client, _ = api()

    resposta = client.get('/health', headers={'x-correlation-id': 'abc-123'})

    assert resposta.headers['x-correlation-id'] == 'abc-123'


def test_listar_orders_sem_cursor_em_pagina_parcial(api):
    client, _ = api(linhas=[_linha_de_pedido()])

    resposta = client.get('/v1/orders')

    payload = resposta.json()
    assert resposta.status_code == 200
    assert len(payload['items']) == 1
    assert payload['next_cursor'] is None


def test_listar_orders_retorna_next_cursor_em_pagina_cheia(api):
    # Arrange — página cheia (itens == page_size) tem próxima página
    linhas = [
        _linha_de_pedido('o1', datetime(2018, 5, 1, 10, 0, 0)),
        _linha_de_pedido('o2', datetime(2018, 5, 2, 10, 0, 0)),
    ]
    client, _ = api(linhas=linhas)

    # Act
    resposta = client.get('/v1/orders', params={'page_size': 2})

    # Assert — cursor aponta para o último item da página
    cursor = resposta.json()['next_cursor']
    assert cursor['after_id'] == 'o2'
    assert cursor['purchased_after'] == '2018-05-02T10:00:00'


def test_listar_orders_envia_params_keyset_na_query(api):
    client, conexao = api()

    client.get(
        '/v1/orders',
        params={
            'purchased_after': '2018-01-01T00:00:00',
            'after_id': 'o9',
            'page_size': 10,
        },
    )

    _, params = conexao.queries[0]
    assert params['purchased_after'] == datetime(2018, 1, 1)
    assert params['after_id'] == 'o9'
    assert params['page_size'] == 10


def test_listar_orders_rejeita_page_size_acima_do_max(api):
    client, _ = api()

    resposta = client.get('/v1/orders', params={'page_size': 1001})

    assert resposta.status_code == 422


def test_listar_orders_rejeita_purchased_after_invalido(api):
    client, _ = api()

    resposta = client.get('/v1/orders', params={'purchased_after': 'ontem'})

    assert resposta.status_code == 422


def test_v1_exige_token_quando_configurado(api):
    # Arrange — API_TOKEN definido liga a exigência do header
    client, _ = api(token='s3gr3d0')

    # Act / Assert — sem token 401; com token correto 200
    assert client.get('/v1/orders').status_code == 401
    ok = client.get('/v1/orders', headers={'x-api-token': 's3gr3d0'})
    assert ok.status_code == 200


def test_health_nao_exige_token(api):
    client, _ = api(token='s3gr3d0')

    assert client.get('/health').status_code == 200


def test_erro_nao_tratado_retorna_500_com_correlation_id(api):
    client, _ = api()
    app = client.app

    async def explode():
        raise RuntimeError('boom')
        yield  # pragma: no cover

    app.dependency_overrides[obter_conexao] = explode
    resposta = client.get('/v1/orders')

    assert resposta.status_code == 500
    assert resposta.json()['correlation_id']


def test_ciclo_de_vida_abre_e_fecha_o_pool(api, monkeypatch):
    monkeypatch.setenv('POOL_MIN_SIZE', '0')
    monkeypatch.setenv('PGPASSWORD', 'x')
    obter_configuracoes.cache_clear()
    app = criar_app()

    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert app.state.pool is not None


def test_resolver_senha_prefere_ambiente():
    settings = Settings(PGPASSWORD='direta', SECRET_ARN='arn:ignorado')

    assert resolver_senha(settings) == 'direta'


def test_resolver_senha_le_do_secrets_manager():
    # Arrange — sem senha no ambiente, com SECRET_ARN configurado
    settings = Settings(PGPASSWORD='', SECRET_ARN='arn:aws:sm:secret')
    fake = mock.Mock()
    fake.get_secret_value.return_value = {'SecretString': '{"password": "do-secret"}'}

    # Act
    with mock.patch('boto3.client', return_value=fake):
        senha = resolver_senha(settings)

    # Assert
    assert senha == 'do-secret'
    fake.get_secret_value.assert_called_once_with(SecretId='arn:aws:sm:secret')


def test_resolver_senha_vazia_sem_fontes():
    settings = Settings(PGPASSWORD='', SECRET_ARN='')

    assert resolver_senha(settings) == ''


def test_criar_pool_nasce_fechado_e_dimensionado():
    settings = Settings(PGPASSWORD='x', POOL_MIN_SIZE=0, POOL_MAX_SIZE=3)

    pool = criar_pool(settings)

    assert pool.min_size == 0
    assert pool.max_size == 3
    assert pool.closed


def test_gerar_token_iam_assina_localmente():
    settings = Settings(PGHOST='db.interno', PGPORT=5432, PGUSER='api_reader')
    fake = mock.Mock()
    fake.generate_db_auth_token.return_value = 'token-iam'

    with mock.patch('boto3.client', return_value=fake):
        token = gerar_token_iam(settings)

    assert token == 'token-iam'
    fake.generate_db_auth_token.assert_called_once_with(
        DBHostname='db.interno', Port=5432, DBUsername='api_reader'
    )


def test_criar_pool_modo_iam_usa_tls_e_pool_iam():
    settings = Settings(DB_AUTH='iam', POOL_MIN_SIZE=0)

    pool = criar_pool(settings)

    assert isinstance(pool, IamAuthPool)
    assert 'sslmode=require' in pool.conninfo


def test_pool_iam_renova_token_a_cada_conexao(monkeypatch):
    # Arrange — pool IAM com o token e o _connect da base trocados por dublês
    settings = Settings(DB_AUTH='iam', POOL_MIN_SIZE=0)
    pool = criar_pool(settings)
    monkeypatch.setattr(database, 'gerar_token_iam', lambda _: 'tok-novo')

    async def connect_falso(self, timeout=None):
        return 'conexao'

    monkeypatch.setattr(AsyncConnectionPool, '_connect', connect_falso)

    # Act
    resultado = asyncio.run(pool._connect())

    # Assert — o token novo entrou como senha da conexão
    assert resultado == 'conexao'
    assert pool.kwargs['password'] == 'tok-novo'
