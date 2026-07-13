"""Agregador de rotas da versão 1 da Event API."""
from fastapi import APIRouter

from src.hot.api_events.api.v1.endpoints import events


def montar_roteador_v1() -> APIRouter:
    """Monta o v1 por aplicação (espelha o padrão da API fria)."""
    api_router = APIRouter()
    api_router.include_router(events.router, prefix='/events', tags=['events'])
    return api_router
