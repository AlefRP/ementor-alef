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

from src.cold.api_orders.api.v1.api import api_router
from src.cold.api_orders.core.configs import get_settings
from src.cold.api_orders.core.database import create_pool
from src.cold.api_orders.core.deps import require_token

logger = logging.getLogger('api_orders')
logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Abre o pool no startup e fecha no shutdown (graceful)."""
    app.state.pool = create_pool(get_settings())
    await app.state.pool.open()
    yield
    await app.state.pool.close()


def create_app() -> FastAPI:
    """Fábrica da aplicação (facilita testes e configuração por ambiente)."""
    settings = get_settings()
    app = FastAPI(title=settings.PROJECT_NAME, version='1.0.0', lifespan=lifespan)
    app.include_router(
        api_router,
        prefix=settings.API_V1_STR,
        dependencies=[Depends(require_token)],
    )

    @app.get('/health', tags=['infra'])
    async def health() -> dict[str, str]:
        """Disponibilidade da API sem tocar o banco (probe da Lambda)."""
        return {'status': 'ok'}

    @app.middleware('http')
    async def observability(request: Request, call_next) -> Response:
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


app = create_app()
