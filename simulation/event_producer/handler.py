"""Lambda produtora de eventos sintéticos de pedidos (SIMULAÇÃO).

Simula o sistema de origem que emite eventos de pedido. NÃO faz parte da
arquitetura: ela apenas bate na fronteira de entrada da camada quente, que é a
**Event API** (EC2) — quem publica no SQS é a API, não este produtor.

Roda DENTRO da VPC (subnets privadas) porque a API é privada: chama o IP fixo da
EC2 por HTTPS e verifica o certificado contra a CA self-signed da API, que chega
inline em ``API_CA_PEM`` (certificado é público, não é segredo; a Lambda fria usa
a mesma CA, lá embarcada no zip).

A geração dos eventos vive em ``simulation/events.py`` (empacotada no zip junto
com o Faker — ver ``make event-producer-bundle``); aqui fica só a orquestração:
montar lotes e entregá-los à API.
"""
import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

from ..events import new_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Teto de eventos por requisição — casa com MAX_EVENTS_POR_REQUISICAO da API.
EVENTS_PER_REQUEST_MAX = 500


def _config() -> dict:
    """Lê a configuração do ambiente a cada invocação (testável)."""
    por_requisicao = int(os.environ.get('EVENTS_PER_REQUEST', '100'))
    return {
        'api_base_url': os.environ['API_BASE_URL'].rstrip('/'),
        'events_per_run': int(os.environ.get('EVENTS_PER_RUN', '60')),
        'events_per_request': min(por_requisicao, EVENTS_PER_REQUEST_MAX),
        'timeout': int(os.environ.get('TIMEOUT_SECONDS', '30')),
        'api_token': os.environ.get('API_TOKEN', ''),
        'ca_pem': os.environ.get('API_CA_PEM', ''),
    }


def _publicar_lote(config: dict, lote: list[dict]) -> int:
    """POST /v1/events — devolve quantos a API confirmou ter enfileirado."""
    url = f"{config['api_base_url']}/v1/events"
    if not url.startswith(('http://', 'https://')):  # NOSONAR
        raise ValueError(f'URL com esquema não suportado: {url}')
    corpo = json.dumps({'events': lote}).encode('utf-8')
    requisicao = urllib.request.Request(
        url, data=corpo, headers={'Content-Type': 'application/json'}
    )
    if config['api_token']:
        requisicao.add_header('x-api-token', config['api_token'])
    contexto = (
        ssl.create_default_context(cadata=config['ca_pem'])
        if config['ca_pem']
        else None
    )
    # B310 suprimido: o esquema http(s) é validado logo acima.
    with urllib.request.urlopen(  # nosec B310
        requisicao, timeout=config['timeout'], context=contexto
    ) as resposta:
        return json.loads(resposta.read())['published']


def handler(event, context):
    """Gera N eventos e os entrega à Event API em lotes."""
    config = _config()
    publicados = 0
    try:
        momento = datetime.now(timezone.utc)
        eventos = [new_event(momento) for _ in range(config['events_per_run'])]
        tamanho = config['events_per_request']
        for inicio in range(0, len(eventos), tamanho):
            publicados += _publicar_lote(config, eventos[inicio : inicio + tamanho])
        logger.info(json.dumps({'event': 'produce_ok', 'published': publicados}))
        return {'statusCode': 200, 'published': publicados}
    except Exception:
        logger.exception(
            json.dumps({'event': 'produce_error', 'published': publicados})
        )
        raise
