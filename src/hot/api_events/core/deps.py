"""Dependências compartilhadas dos endpoints (fila e autenticação)."""
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from src.hot.api_events.core.configs import obter_configuracoes


def obter_cliente_sqs(request: Request):
    """Devolve o client SQS aberto no lifespan da aplicação."""
    return request.app.state.sqs


def exigir_token(
    x_api_token: Annotated[str | None, Header()] = None,
) -> None:
    """Valida o token estático quando configurado (defesa em profundidade)."""
    esperado = obter_configuracoes().API_TOKEN
    if not esperado:
        return
    if not (x_api_token and secrets.compare_digest(x_api_token, esperado)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token de API ausente ou inválido.',
        )
