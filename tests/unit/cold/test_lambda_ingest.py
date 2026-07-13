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
def ambiente_da_lambda(monkeypatch):
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


def _pedido(order_id, purchased):
    return {
        'order_id': order_id,
        'order_status': 'delivered',
        'order_purchase_timestamp': purchased,
    }


def _chaves_do_bucket():
    cliente = boto3.client('s3')
    resultado = cliente.list_objects_v2(Bucket=BUCKET)
    return [item['Key'] for item in resultado.get('Contents', [])]


@mock_aws
def test_handler_ingere_paginas_e_atualiza_marker(ambiente_da_lambda):
    # Arrange — duas páginas da API; a segunda é a última (menor que page_size)
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    paginas = [
        {
            'items': [
                _pedido('o1', '2018-05-01T10:00:00'),
                _pedido('o2', '2018-05-02T10:00:00'),
            ]
        },
        {'items': [_pedido('o3', '2018-05-03T10:00:00')]},
    ]

    # Act
    with mock.patch.object(ingest, '_buscar_pagina', side_effect=paginas):
        resultado = ingest.handler({}, None)

    # Assert
    assert resultado == {'statusCode': 200, 'ingested': 3, 'pages': 2}
    chaves_de_dados = [k for k in _chaves_do_bucket() if k.startswith('orders/')]
    assert len(chaves_de_dados) == 2
    for chave in chaves_de_dados:
        assert re.match(r'^orders/year=\d{4}/month=\d{2}/day=\d{2}/', chave)
    marker = json.loads(
        boto3.client('s3')
        .get_object(Bucket=BUCKET, Key='_markers/orders.json')['Body']
        .read()
    )
    assert marker == {'purchased_after': '2018-05-03T10:00:00', 'after_id': 'o3'}


@mock_aws
def test_handler_retoma_do_marker_salvo(ambiente_da_lambda):
    # Arrange — marker já salvo de uma execução anterior
    cliente = boto3.client('s3')
    cliente.create_bucket(Bucket=BUCKET)
    salvo = {'purchased_after': '2018-06-01T00:00:00', 'after_id': 'o42'}
    cliente.put_object(
        Bucket=BUCKET, Key='_markers/orders.json', Body=json.dumps(salvo).encode()
    )

    # Act
    with mock.patch.object(
        ingest, '_buscar_pagina', return_value={'items': []}
    ) as buscar:
        ingest.handler({}, None)

    # Assert — a primeira busca parte do cursor salvo
    assert buscar.call_args[0][1] == salvo


@mock_aws
def test_handler_sem_dados_novos_nao_grava_nada(ambiente_da_lambda):
    boto3.client('s3').create_bucket(Bucket=BUCKET)

    with mock.patch.object(ingest, '_buscar_pagina', return_value={'items': []}):
        resultado = ingest.handler({}, None)

    assert resultado == {'statusCode': 200, 'ingested': 0, 'pages': 0}
    assert _chaves_do_bucket() == []


@mock_aws
def test_handler_para_no_max_pages(ambiente_da_lambda, monkeypatch):
    monkeypatch.setenv('MAX_PAGES', '1')
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    pagina_cheia = {
        'items': [
            _pedido('o1', '2018-05-01T10:00:00'),
            _pedido('o2', '2018-05-02T10:00:00'),
        ]
    }

    with mock.patch.object(
        ingest, '_buscar_pagina', return_value=pagina_cheia
    ) as buscar:
        resultado = ingest.handler({}, None)

    assert buscar.call_count == 1
    assert resultado['pages'] == 1


@mock_aws
def test_handler_propaga_erro_da_api(ambiente_da_lambda):
    boto3.client('s3').create_bucket(Bucket=BUCKET)

    with mock.patch.object(
        ingest, '_buscar_pagina', side_effect=RuntimeError('API fora')
    ):
        with pytest.raises(RuntimeError):
            ingest.handler({}, None)

    assert _chaves_do_bucket() == []


@mock_aws
def test_handler_propaga_erro_do_s3(ambiente_da_lambda):
    # Bucket não existe: o put_object da primeira página deve falhar alto.
    pagina = {'items': [_pedido('o1', '2018-05-01T10:00:00')]}

    with mock.patch.object(ingest, '_buscar_pagina', return_value=pagina):
        with pytest.raises(ClientError):
            ingest.handler({}, None)


def test_buscar_pagina_monta_url_com_cursor_e_token(ambiente_da_lambda, monkeypatch):
    # Arrange — captura a requisição que a Lambda faria à API
    monkeypatch.setenv('API_TOKEN', 'tok3n')
    capturado = {}

    class FakeResposta:
        def read(self):
            return json.dumps({'items': []}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen_falso(requisicao, timeout=None, context=None):
        capturado['url'] = requisicao.full_url
        capturado['token'] = requisicao.get_header('X-api-token')
        return FakeResposta()

    monkeypatch.setattr(ingest.urllib.request, 'urlopen', urlopen_falso)
    marker = {'purchased_after': '2018-01-01T00:00:00', 'after_id': 'o7'}

    # Act
    corpo = ingest._buscar_pagina(ingest._configuracao(), marker)

    # Assert
    assert corpo == {'items': []}
    assert 'purchased_after=2018-01-01T00%3A00%3A00' in capturado['url']
    assert 'after_id=o7' in capturado['url']
    assert 'page_size=2' in capturado['url']
    assert capturado['token'] == 'tok3n'


def test_buscar_pagina_rejeita_esquema_nao_suportado(ambiente_da_lambda, monkeypatch):
    monkeypatch.setenv('API_BASE_URL', 'ftp://interno')
    marker = {'purchased_after': ingest.KEYSET_START, 'after_id': ''}

    with pytest.raises(ValueError):
        ingest._buscar_pagina(ingest._configuracao(), marker)


def test_chave_raw_particiona_por_data_de_execucao():
    momento = datetime(2026, 7, 7, 13, 45, 9, 123456, tzinfo=timezone.utc)

    chave = ingest._chave_raw('orders', 3, momento)

    assert chave == 'orders/year=2026/month=07/day=07/134509-123456-page0003.json'


@mock_aws
def test_handler_modo_pk_ingere_e_grava_marker_opaco(ambiente_da_lambda):
    boto3.client('s3').create_bucket(Bucket=BUCKET)
    paginas = [
        {
            'items': [{'customer_id': 'c1'}, {'customer_id': 'c2'}],
            'next_cursor': ['c2'],
        },
        {'items': []},
    ]
    evento = {'dataset': 'customers', 'cursor_mode': 'pk'}

    with mock.patch.object(ingest, '_buscar_pagina', side_effect=paginas):
        resultado = ingest.handler(evento, None)

    assert resultado == {'statusCode': 200, 'ingested': 2, 'pages': 1}
    assert any(k.startswith('customers/year=') for k in _chaves_do_bucket())
    marker = json.loads(
        boto3.client('s3')
        .get_object(Bucket=BUCKET, Key='_markers/customers.json')['Body']
        .read()
    )
    assert marker == {'after': ['c2']}


@mock_aws
def test_handler_modo_pk_retoma_do_marker_salvo(ambiente_da_lambda):
    cliente = boto3.client('s3')
    cliente.create_bucket(Bucket=BUCKET)
    salvo = {'after': ['c42']}
    cliente.put_object(
        Bucket=BUCKET, Key='_markers/customers.json', Body=json.dumps(salvo).encode()
    )
    evento = {'dataset': 'customers', 'cursor_mode': 'pk'}

    with mock.patch.object(
        ingest, '_buscar_pagina', return_value={'items': []}
    ) as buscar:
        ingest.handler(evento, None)

    assert buscar.call_args[0][1] == salvo


def test_buscar_pagina_modo_pk_repete_params_after(ambiente_da_lambda, monkeypatch):
    capturado = {}

    class FakeResposta:
        def read(self):
            return json.dumps({'items': []}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen_falso(requisicao, timeout=None, context=None):
        capturado['url'] = requisicao.full_url
        return FakeResposta()

    monkeypatch.setattr(ingest.urllib.request, 'urlopen', urlopen_falso)
    configuracao = ingest._configuracao({'dataset': 'order_items', 'cursor_mode': 'pk'})

    corpo = ingest._buscar_pagina(configuracao, {'after': ['o1', '2']})

    assert corpo == {'items': []}
    assert '/v1/order_items?' in capturado['url']
    assert 'after=o1&after=2' in capturado['url']
    assert 'page_size=2' in capturado['url']


def test_configuracao_com_evento_sobrepoe_ambiente(ambiente_da_lambda):
    configuracao = ingest._configuracao(
        {'dataset': 'sellers', 'cursor_mode': 'pk', 'page_size': 7}
    )

    assert configuracao['dataset'] == 'sellers'
    assert configuracao['cursor_mode'] == 'pk'
    assert configuracao['page_size'] == 7


def test_avancar_marker_pk_mantem_marker_sem_cursor(ambiente_da_lambda):
    # Defensivo: sem next_cursor não há como avançar — mantém o cursor.
    configuracao = {'cursor_mode': 'pk'}
    marker = {'after': ['x']}
    corpo = {'items': [{'customer_id': 'c9'}]}

    assert ingest._avancar_marker(configuracao, marker, corpo) == marker
