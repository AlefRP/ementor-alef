"""Dependências compartilhadas dos endpoints (conexão e autenticação)."""
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

import psycopg
from fastapi import Header, HTTPException, Request, status

from src.cold.api_fastapi.core.configs import get_settings


async def get_connection(
    request: Request,
) -> AsyncIterator[psycopg.AsyncConnection]:
    """Empresta uma conexão do pool da aplicação durante o request."""
    async with request.app.state.pool.connection() as conn:
        yield conn


async def require_token(
    x_api_token: Annotated[str | None, Header()] = None,
) -> None:
    """Valida o token estático quando configurado (defesa em profundidade)."""
    expected = get_settings().API_TOKEN
    if not expected:
        return
    if not (x_api_token and secrets.compare_digest(x_api_token, expected)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token de API ausente ou inválido.',
        )
