"""Lambda de ingestão fria: consome a API de data product e grava na raw (S3).

Agendada via EventBridge; incremental e retomável via marker (o cursor keyset
da API) em ``s3://<raw>/_markers/<dataset>.json``. Uma única função atende
todos os datasets: cada regra do EventBridge passa no input o ``dataset`` e o
``cursor_mode`` — ``orders`` (cursor por timestamp de compra, contrato do
``/v1/orders``) ou ``pk`` (cursor opaco ``after``/``next_cursor`` dos demais
``/v1/<dataset>``). O tráfego é privado: a Lambda roda na VPC, chama a API
pelo IP privado da EC2 (HTTPS com CA própria via ``API_CA_FILE``) e escreve no
S3 pelo gateway endpoint — sem NAT. Módulo autocontido (stdlib + boto3).
"""
import json
import logging
import os
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

KEYSET_START = '1900-01-01T00:00:00'

_S3 = None


def _cliente_s3():
    """Client S3 reaproveitado entre invocações warm."""
    global _S3
    if _S3 is None:
        _S3 = boto3.client('s3')
    return _S3


def _configuracao(event: dict | None = None) -> dict:
    """Configuração do ambiente, sobreposta pelo input do EventBridge.

    O input do alvo (``{"dataset": ..., "cursor_mode": ...}``) permite que uma
    única função atenda N datasets — cada regra injeta o seu.
    """
    configuracao = {
        'api_base_url': os.environ['API_BASE_URL'].rstrip('/'),
        'raw_bucket': os.environ['RAW_BUCKET'],
        'dataset': os.environ.get('DATASET', 'orders'),
        'cursor_mode': os.environ.get('CURSOR_MODE', 'orders'),
        'page_size': os.environ.get('PAGE_SIZE', '500'),
        'max_pages': os.environ.get('MAX_PAGES', '50'),
        'timeout': int(os.environ.get('TIMEOUT_SECONDS', '30')),
        'api_token': os.environ.get('API_TOKEN', ''),
        'ca_file': os.environ.get('API_CA_FILE', ''),
    }
    for chave in ('dataset', 'cursor_mode', 'page_size', 'max_pages'):
        if event and chave in event:
            configuracao[chave] = event[chave]
    configuracao['page_size'] = int(configuracao['page_size'])
    configuracao['max_pages'] = int(configuracao['max_pages'])
    return configuracao


def _chave_do_marker(dataset: str) -> str:
    return f'_markers/{dataset}.json'


def _marker_inicial(cursor_mode: str) -> dict:
    if cursor_mode == 'pk':
        return {'after': []}
    return {'purchased_after': KEYSET_START, 'after_id': ''}


def _ler_marker(bucket: str, dataset: str, cursor_mode: str) -> dict:
    """Cursor da última execução; começa do início se ainda não existir."""
    cliente = _cliente_s3()
    try:
        resposta = cliente.get_object(Bucket=bucket, Key=_chave_do_marker(dataset))
    except cliente.exceptions.NoSuchKey:
        return _marker_inicial(cursor_mode)
    return json.loads(resposta['Body'].read())


def _buscar_pagina(configuracao: dict, marker: dict) -> dict:
    """Busca uma página da API respeitando o cursor keyset."""
    if configuracao['cursor_mode'] == 'pk':
        pares = [('after', valor) for valor in marker['after']]
        pares.append(('page_size', configuracao['page_size']))
        query = urllib.parse.urlencode(pares)
    else:
        query = urllib.parse.urlencode(
            {
                'purchased_after': marker['purchased_after'],
                'after_id': marker['after_id'],
                'page_size': configuracao['page_size'],
            }
        )
    url = f"{configuracao['api_base_url']}/v1/{configuracao['dataset']}?{query}"
    # S5332 suprimido: http em claro é decisão do lab — a API é interna à
    # VPC (subnet privada + security group), sem TLS no serviço interno.
    if not url.startswith(('http://', 'https://')):  # NOSONAR
        raise ValueError(f'URL com esquema não suportado: {url}')
    requisicao = urllib.request.Request(url)
    if configuracao['api_token']:
        requisicao.add_header('x-api-token', configuracao['api_token'])
    contexto = (
        ssl.create_default_context(cafile=configuracao['ca_file'])
        if configuracao['ca_file']
        else None
    )
    # B310 suprimido: o esquema http(s) é validado logo acima.
    with urllib.request.urlopen(  # nosec B310
        requisicao, timeout=configuracao['timeout'], context=contexto
    ) as resposta:
        return json.loads(resposta.read())


def _chave_raw(dataset: str, pagina: int, momento: datetime) -> str:
    """Chave particionada pela data de execução (year/month/day)."""
    return (
        f'{dataset}/year={momento:%Y}/month={momento:%m}/day={momento:%d}/'
        f'{momento:%H%M%S}-{momento.microsecond:06d}-page{pagina:04d}.json'
    )


def _avancar_marker(configuracao: dict, marker: dict, corpo: dict) -> dict:
    """Próximo cursor: ecoa o next_cursor (pk) ou deriva do último item."""
    if configuracao['cursor_mode'] == 'pk':
        proximo_cursor = corpo.get('next_cursor')
        return {'after': proximo_cursor} if proximo_cursor else marker
    ultimo = corpo['items'][-1]
    return {
        'purchased_after': ultimo['order_purchase_timestamp'],
        'after_id': ultimo['order_id'],
    }


def handler(event, context):
    """Ingere um dataset da API para a raw e avança o marker (retomável)."""
    configuracao = _configuracao(event)
    try:
        marker = _ler_marker(
            configuracao['raw_bucket'],
            configuracao['dataset'],
            configuracao['cursor_mode'],
        )
        inicio = datetime.now(timezone.utc)
        ingeridos = 0
        paginas = 0
        for pagina in range(1, configuracao['max_pages'] + 1):
            corpo = _buscar_pagina(configuracao, marker)
            itens = corpo.get('items', [])
            if not itens:
                break
            _cliente_s3().put_object(
                Bucket=configuracao['raw_bucket'],
                Key=_chave_raw(configuracao['dataset'], pagina, inicio),
                Body=json.dumps(itens, default=str).encode('utf-8'),
            )
            ingeridos += len(itens)
            paginas += 1
            marker = _avancar_marker(configuracao, marker, corpo)
            if len(itens) < configuracao['page_size']:
                break
        if ingeridos:
            _cliente_s3().put_object(
                Bucket=configuracao['raw_bucket'],
                Key=_chave_do_marker(configuracao['dataset']),
                Body=json.dumps(marker).encode('utf-8'),
            )
        logger.info(
            json.dumps(
                {
                    'event': 'ingest_ok',
                    'dataset': configuracao['dataset'],
                    'ingested': ingeridos,
                    'pages': paginas,
                    'marker': marker,
                }
            )
        )
        return {'statusCode': 200, 'ingested': ingeridos, 'pages': paginas}
    except Exception:
        logger.exception(
            json.dumps({'event': 'ingest_error', 'dataset': configuracao['dataset']})
        )
        raise
