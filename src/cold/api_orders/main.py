"""Aplicação FastAPI da camada fria — data product Olist sobre o RDS.

Padrões adotados: lifespan abre/fecha o pool async (psycopg_pool),
correlation id por request e logs estruturados em JSON. O tráfego é privado
(VPC); com ``API_TOKEN`` definido, o v1 exige o header ``x-api-token``.
"""
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from src.cold.api_orders.api.v1.api import montar_roteador_v1
from src.cold.api_orders.core.configs import Settings, obter_configuracoes
from src.cold.api_orders.core.database import criar_pool
from src.cold.api_orders.core.deps import exigir_token

logger = logging.getLogger('api_orders')
logger.setLevel(logging.INFO)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Abre o pool no startup e fecha no shutdown (graceful)."""
    app.state.pool = criar_pool(obter_configuracoes())
    await app.state.pool.open()
    yield
    await app.state.pool.close()


def _inicializar_cache(settings: Settings) -> None:
    """Cache-aside: in-memory (1 instância) ou Redis quando REDIS_URL existir."""
    if settings.REDIS_URL:
        # Import tardio: redis só é dependência quando o backend é usado
        # (instale fastapi-cache2[redis] junto com a configuração).
        from fastapi_cache.backends.redis import RedisBackend
        from redis import asyncio as aioredis

        backend = RedisBackend(aioredis.from_url(settings.REDIS_URL))
    else:
        backend = InMemoryBackend()
        # O store do backend in-memory é compartilhado no nível da classe;
        # um dict próprio isola o cache desta aplicação (e cada app de teste).
        backend._store = {}
    # init é no-op quando já inicializado (estado de classe): o reset garante
    # que cada app criado (1 por processo em produção; N nos testes) comece
    # com o backend recém-configurado, sem herdar cache de outro app.
    FastAPICache.reset()
    FastAPICache.init(
        backend,
        prefix='api-cache',
        expire=settings.CACHE_TTL_SECONDS,
        enable=settings.CACHE_TTL_SECONDS > 0,
    )


def criar_app() -> FastAPI:
    """Fábrica da aplicação (facilita testes e configuração por ambiente)."""
    settings = obter_configuracoes()
    app = FastAPI(title=settings.PROJECT_NAME, version='1.0.0', lifespan=ciclo_de_vida)
    _inicializar_cache(settings)
    app.include_router(
        montar_roteador_v1(settings.CACHE_TTL_SECONDS),
        prefix=settings.API_V1_STR,
        dependencies=[Depends(exigir_token)],
    )

    @app.get('/health', tags=['infra'])
    async def saude() -> dict[str, str]:
        """Disponibilidade da API sem tocar o banco (probe da Lambda)."""
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
