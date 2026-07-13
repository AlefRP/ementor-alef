"""Publicação dos eventos na fila — a fronteira de entrada da camada quente.

O corpo da mensagem é o evento JSON puro, exatamente como a Lambda de ingestão
quente o espera (``json.loads(record['body'])``): a API é um portão de entrada
validado, não um transformador do payload.
"""
import json

from src.hot.api_events.core.configs import SQS_BATCH_MAX


def publicar_eventos(cliente, queue_url: str, eventos: list[dict]) -> int:
    """Publica os eventos em lotes de até 10 e devolve o total publicado.

    Rejeição parcial vira exceção: o SQS confirma mensagem a mensagem, e aceitar
    silenciosamente um lote incompleto perderia eventos sem deixar rastro.
    """
    publicados = 0
    for inicio in range(0, len(eventos), SQS_BATCH_MAX):
        lote = eventos[inicio : inicio + SQS_BATCH_MAX]
        entradas = [
            {'Id': str(indice), 'MessageBody': json.dumps(evento)}
            for indice, evento in enumerate(lote)
        ]
        resposta = cliente.send_message_batch(QueueUrl=queue_url, Entries=entradas)
        rejeitadas = resposta.get('Failed', [])
        if rejeitadas:
            raise RuntimeError(f'{len(rejeitadas)} mensagens rejeitadas pelo SQS')
        publicados += len(lote)
    return publicados
