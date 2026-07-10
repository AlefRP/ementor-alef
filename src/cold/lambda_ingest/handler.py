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


def _s3_client():
    """Client S3 reaproveitado entre invocações warm."""
    global _S3
    if _S3 is None:
        _S3 = boto3.client('s3')
    return _S3


def _config(event: dict | None = None) -> dict:
    """Configuração do ambiente, sobreposta pelo input do EventBridge.

    O input do alvo (``{"dataset": ..., "cursor_mode": ...}``) permite que uma
    única função atenda N datasets — cada regra injeta o seu.
    """
    config = {
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
    for key in ('dataset', 'cursor_mode', 'page_size', 'max_pages'):
        if event and key in event:
            config[key] = event[key]
    config['page_size'] = int(config['page_size'])
    config['max_pages'] = int(config['max_pages'])
    return config


def _marker_key(dataset: str) -> str:
    return f'_markers/{dataset}.json'


def _initial_marker(cursor_mode: str) -> dict:
    if cursor_mode == 'pk':
        return {'after': []}
    return {'purchased_after': KEYSET_START, 'after_id': ''}


def _read_marker(bucket: str, dataset: str, cursor_mode: str) -> dict:
    """Cursor da última execução; começa do início se ainda não existir."""
    client = _s3_client()
    try:
        response = client.get_object(Bucket=bucket, Key=_marker_key(dataset))
    except client.exceptions.NoSuchKey:
        return _initial_marker(cursor_mode)
    return json.loads(response['Body'].read())


def _fetch_page(config: dict, marker: dict) -> dict:
    """Busca uma página da API respeitando o cursor keyset."""
    if config['cursor_mode'] == 'pk':
        pairs = [('after', value) for value in marker['after']]
        pairs.append(('page_size', config['page_size']))
        query = urllib.parse.urlencode(pairs)
    else:
        query = urllib.parse.urlencode(
            {
                'purchased_after': marker['purchased_after'],
                'after_id': marker['after_id'],
                'page_size': config['page_size'],
            }
        )
    url = f"{config['api_base_url']}/v1/{config['dataset']}?{query}"
    # S5332 suprimido: http em claro é decisão do lab — a API é interna à
    # VPC (subnet privada + security group), sem TLS no serviço interno.
    if not url.startswith(('http://', 'https://')):  # NOSONAR
        raise ValueError(f'URL com esquema não suportado: {url}')
    request = urllib.request.Request(url)
    if config['api_token']:
        request.add_header('x-api-token', config['api_token'])
    context = (
        ssl.create_default_context(cafile=config['ca_file'])
        if config['ca_file']
        else None
    )
    # B310 suprimido: o esquema http(s) é validado logo acima.
    with urllib.request.urlopen(  # nosec B310
        request, timeout=config['timeout'], context=context
    ) as response:
        return json.loads(response.read())


def _raw_key(dataset: str, page: int, moment: datetime) -> str:
    """Chave particionada pela data de execução (year/month/day)."""
    return (
        f'{dataset}/year={moment:%Y}/month={moment:%m}/day={moment:%d}/'
        f'{moment:%H%M%S}-{moment.microsecond:06d}-page{page:04d}.json'
    )


def _advance_marker(config: dict, marker: dict, body: dict) -> dict:
    """Próximo cursor: ecoa o next_cursor (pk) ou deriva do último item."""
    if config['cursor_mode'] == 'pk':
        next_cursor = body.get('next_cursor')
        return {'after': next_cursor} if next_cursor else marker
    last = body['items'][-1]
    return {
        'purchased_after': last['order_purchase_timestamp'],
        'after_id': last['order_id'],
    }


def handler(event, context):
    """Ingere um dataset da API para a raw e avança o marker (retomável)."""
    config = _config(event)
    try:
        marker = _read_marker(
            config['raw_bucket'], config['dataset'], config['cursor_mode']
        )
        started = datetime.now(timezone.utc)
        ingested = 0
        pages = 0
        for page in range(1, config['max_pages'] + 1):
            body = _fetch_page(config, marker)
            items = body.get('items', [])
            if not items:
                break
            _s3_client().put_object(
                Bucket=config['raw_bucket'],
                Key=_raw_key(config['dataset'], page, started),
                Body=json.dumps(items, default=str).encode('utf-8'),
            )
            ingested += len(items)
            pages += 1
            marker = _advance_marker(config, marker, body)
            if len(items) < config['page_size']:
                break
        if ingested:
            _s3_client().put_object(
                Bucket=config['raw_bucket'],
                Key=_marker_key(config['dataset']),
                Body=json.dumps(marker).encode('utf-8'),
            )
        logger.info(
            json.dumps(
                {
                    'event': 'ingest_ok',
                    'dataset': config['dataset'],
                    'ingested': ingested,
                    'pages': pages,
                    'marker': marker,
                }
            )
        )
        return {'statusCode': 200, 'ingested': ingested, 'pages': pages}
    except Exception:
        logger.exception(
            json.dumps({'event': 'ingest_error', 'dataset': config['dataset']})
        )
        raise
