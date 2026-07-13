"""Testes da Event API (fronteira de entrada da camada quente)."""
from contextlib import ExitStack
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.hot.api_events import main as modulo_da_api
from src.hot.api_events.core.configs import obter_configuracoes
from src.hot.api_events.main import criar_app

FILA = 'https://sqs.us-east-1.amazonaws.com/000000000000/eventos'


class FilaFalsa:
    """Client SQS de mentira: guarda os lotes e simula rejeição parcial."""

    def __init__(self, falhas_do_primeiro_lote=()):
        self.lotes = []
        self.falhas_do_primeiro_lote = list(falhas_do_primeiro_lote)
        self.fechada = False

    def send_message_batch(self, QueueUrl, Entries):  # noqa: N803 (contrato boto3)
        self.lotes.append(Entries)
        if len(self.lotes) == 1 and self.falhas_do_primeiro_lote:
            return {'Failed': self.falhas_do_primeiro_lote}
        return {}

    def close(self):
        self.fechada = True


def evento(event_id='e1', event_type='order_created'):
    """Evento válido no contrato do /v1/events."""
    return {
        'event_id': event_id,
        'event_type': event_type,
        'event_timestamp': datetime(
            2026, 7, 13, 12, 0, tzinfo=timezone.utc
        ).isoformat(),
        'customer': {
            'customer_unique_id': 'c1',
            'customer_name': 'Fulano',
            'customer_city': 'Sao Paulo',
            'customer_state': 'SP',
            'customer_zip_code_prefix': '01310',
        },
        'order': {
            'order_id': 'o1',
            'product_category_name': 'cama_mesa_banho',
            'product_name': 'Lencol',
            'items_count': 2,
            'price': 100.0,
            'freight_value': 15.5,
        },
        'payment': {'payment_type': 'credit_card', 'payment_installments': 3},
    }


@pytest.fixture()
def api(monkeypatch):
    """App com a fila falsa no lugar do client boto3 aberto no lifespan."""
    obter_configuracoes.cache_clear()
    monkeypatch.setenv('QUEUE_URL', FILA)

    with ExitStack() as pilha:

        def fabrica(fila=None, token=''):
            fila = fila or FilaFalsa()
            if token:
                monkeypatch.setenv('API_TOKEN', token)
            obter_configuracoes.cache_clear()
            monkeypatch.setattr(modulo_da_api.boto3, 'client', lambda _servico: fila)
            # TestClient como context manager: sem isso o lifespan não roda e o
            # app.state.sqs (que os endpoints leem) nunca seria criado.
            cliente = pilha.enter_context(TestClient(criar_app()))
            return cliente, fila

        yield fabrica

    obter_configuracoes.cache_clear()


def test_health_responde_sem_tocar_a_fila(api):
    # Arrange
    cliente, fila = api()

    # Act
    resposta = cliente.get('/health')

    # Assert
    assert resposta.status_code == 200
    assert resposta.json() == {'status': 'ok'}
    assert fila.lotes == []


def test_publicar_eventos_enfileira_o_lote_e_devolve_202(api):
    # Arrange
    cliente, fila = api()

    # Act
    resposta = cliente.post('/v1/events', json={'events': [evento(), evento('e2')]})

    # Assert
    assert resposta.status_code == 202
    assert resposta.json()['published'] == 2
    assert len(fila.lotes) == 1
    assert len(fila.lotes[0]) == 2


def test_publicar_eventos_quebra_em_lotes_de_dez(api):
    # Arrange — 25 eventos: o SQS aceita no máximo 10 por send_message_batch.
    cliente, fila = api()
    eventos = [evento(f'e{indice}') for indice in range(25)]

    # Act
    resposta = cliente.post('/v1/events', json={'events': eventos})

    # Assert
    assert resposta.status_code == 202
    assert resposta.json()['published'] == 25
    assert [len(lote) for lote in fila.lotes] == [10, 10, 5]


def test_publicar_eventos_devolve_502_quando_a_fila_rejeita(api):
    # Arrange — rejeição parcial: aceitar em silêncio perderia o evento.
    cliente, fila = api(FilaFalsa(falhas_do_primeiro_lote=[{'Id': '0'}]))

    # Act
    resposta = cliente.post('/v1/events', json={'events': [evento()]})

    # Assert
    assert resposta.status_code == 502
    assert 'fila' in resposta.json()['detail']


def test_publicar_eventos_rejeita_contrato_invalido(api):
    # Arrange — items_count zero viola o ge=1 do schema.
    cliente, fila = api()
    invalido = evento()
    invalido['order']['items_count'] = 0

    # Act
    resposta = cliente.post('/v1/events', json={'events': [invalido]})

    # Assert — 422 (contrato), não 502 (fila): nada chegou a ser publicado.
    assert resposta.status_code == 422
    assert fila.lotes == []


def test_publicar_eventos_rejeita_lote_vazio(api):
    # Arrange
    cliente, fila = api()

    # Act
    resposta = cliente.post('/v1/events', json={'events': []})

    # Assert
    assert resposta.status_code == 422
    assert fila.lotes == []


def test_v1_exige_token_quando_configurado(api):
    # Arrange
    cliente, fila = api(token='segredo')

    # Act
    sem_token = cliente.post('/v1/events', json={'events': [evento()]})
    com_token = cliente.post(
        '/v1/events',
        json={'events': [evento()]},
        headers={'x-api-token': 'segredo'},
    )

    # Assert
    assert sem_token.status_code == 401
    assert com_token.status_code == 202
    assert len(fila.lotes) == 1


def test_correlation_id_do_request_volta_na_resposta(api):
    # Arrange
    cliente, _ = api()

    # Act
    resposta = cliente.post(
        '/v1/events',
        json={'events': [evento()]},
        headers={'x-correlation-id': 'trilha-123'},
    )

    # Assert
    assert resposta.headers['x-correlation-id'] == 'trilha-123'
    assert resposta.json()['correlation_id'] == 'trilha-123'
