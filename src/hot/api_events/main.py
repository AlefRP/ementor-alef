"""Aplicação FastAPI da camada quente — portão de entrada dos eventos.

Espelha os padrões da API fria (lifespan, correlation id, log JSON), trocando
o pool do Postgres pelo client do SQS: aqui a API não lê dados, ela ACEITA
eventos, valida o contrato e os entrega à fila. O tráfego é privado (VPC) e,
com ``API_TOKEN`` definido, o v1 exige o header ``x-api-token``.
"""
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import boto3
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from src.hot.api_events.api.v1.api import montar_roteador_v1
from src.hot.api_events.core.configs import obter_configuracoes
from src.hot.api_events.core.deps import exigir_token

logger = logging.getLogger('api_events')
logger.setLevel(logging.INFO)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Cria o client SQS no startup (reaproveita conexões TLS entre requests)."""
    app.state.sqs = boto3.client('sqs')
    yield
    app.state.sqs.close()


def criar_app() -> FastAPI:
    """Fábrica da aplicação (facilita testes e configuração por ambiente)."""
    settings = obter_configuracoes()
    app = FastAPI(title=settings.PROJECT_NAME, version='1.0.0', lifespan=ciclo_de_vida)
    app.include_router(
        montar_roteador_v1(),
        prefix=settings.API_V1_STR,
        dependencies=[Depends(exigir_token)],
    )

    @app.get('/health', tags=['infra'])
    async def saude() -> dict[str, str]:
        """Disponibilidade da API sem tocar a fila (probe do produtor)."""
        return {'status': 'ok'}

    @app.middleware('http')
    async def observabilidade(request: Request, call_next) -> Response:
        """Correlation id + access log JSON + resposta 500 padronizada."""
        cid = request.headers.get('x-correlation-id') or str(uuid.uuid4())
        request.state.correlation_id = cid
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                json.dumps(
                    {
                        'event': 'request_error',
                        'path': request.url.path,
                        'correlation_id': cid,
                    }
                )
            )
            response = JSONResponse(
                status_code=500,
                content={'detail': 'erro interno', 'correlation_id': cid},
            )
        response.headers['x-correlation-id'] = cid
        logger.info(
            json.dumps(
                {
                    'event': 'request',
                    'method': request.method,
                    'path': request.url.path,
                    'status': response.status_code,
                    'duration_ms': round((time.perf_counter() - started) * 1000, 2),
                    'correlation_id': cid,
                }
            )
        )
        return response

    return app


app = criar_app()
