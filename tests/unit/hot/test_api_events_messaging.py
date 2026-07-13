"""Testes da publicação no SQS (core/messaging da Event API)."""
import json

import pytest

from src.hot.api_events.core.messaging import publicar_eventos

FILA = 'https://sqs.us-east-1.amazonaws.com/000000000000/eventos'


class FilaFalsa:
    def __init__(self, falhas_do_primeiro_lote=()):
        self.lotes = []
        self.falhas_do_primeiro_lote = list(falhas_do_primeiro_lote)

    def send_message_batch(self, QueueUrl, Entries):  # noqa: N803 (contrato boto3)
        self.lotes.append({'url': QueueUrl, 'entradas': Entries})
        if len(self.lotes) == 1 and self.falhas_do_primeiro_lote:
            return {'Failed': self.falhas_do_primeiro_lote}
        return {}


def test_publicar_eventos_envia_o_corpo_como_json_puro():
    # Arrange — a Lambda de ingestão faz json.loads(body): o corpo é o evento.
    fila = FilaFalsa()
    eventos = [{'event_id': 'e1', 'event_type': 'order_created'}]

    # Act
    publicados = publicar_eventos(fila, FILA, eventos)

    # Assert
    assert publicados == 1
    entrada = fila.lotes[0]['entradas'][0]
    assert fila.lotes[0]['url'] == FILA
    assert json.loads(entrada['MessageBody']) == eventos[0]


def test_publicar_eventos_respeita_o_limite_de_dez_por_lote():
    # Arrange — 23 eventos: o send_message_batch do SQS aceita 10 por chamada.
    fila = FilaFalsa()
    eventos = [{'event_id': f'e{indice}'} for indice in range(23)]

    # Act
    publicados = publicar_eventos(fila, FILA, eventos)

    # Assert
    assert publicados == 23
    assert [len(lote['entradas']) for lote in fila.lotes] == [10, 10, 3]


def test_publicar_eventos_numera_as_entradas_dentro_do_lote():
    # Arrange — o Id é local ao lote; repetir Id faria o SQS recusar a chamada.
    fila = FilaFalsa()
    eventos = [{'event_id': f'e{indice}'} for indice in range(12)]

    # Act
    publicar_eventos(fila, FILA, eventos)

    # Assert
    for lote in fila.lotes:
        ids = [entrada['Id'] for entrada in lote['entradas']]
        assert ids == [str(indice) for indice in range(len(ids))]


def test_publicar_eventos_explode_quando_a_fila_rejeita_parcialmente():
    # Arrange — aceitar um lote incompleto perderia evento sem deixar rastro.
    fila = FilaFalsa(falhas_do_primeiro_lote=[{'Id': '3'}])

    # Act / Assert
    with pytest.raises(RuntimeError, match='rejeitadas'):
        publicar_eventos(fila, FILA, [{'event_id': 'e1'}])


def test_publicar_eventos_sem_eventos_nao_chama_a_fila():
    # Arrange
    fila = FilaFalsa()

    # Act
    publicados = publicar_eventos(fila, FILA, [])

    # Assert
    assert publicados == 0
    assert fila.lotes == []
