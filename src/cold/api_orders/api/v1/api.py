"""Agregador de rotas da versão 1 da API."""
from fastapi import APIRouter

from src.cold.api_orders.api.v1.endpoints import datasets, orders


def build_api_router(cache_ttl: int) -> APIRouter:
    """Monta o v1 por aplicação (o TTL do cache é decisão de configuração)."""
    api_router = APIRouter()
    api_router.include_router(orders.router, prefix='/orders', tags=['orders'])
    for spec in datasets.SPECS:
        api_router.include_router(
            datasets.build_router(spec, cache_ttl),
            prefix=f'/{spec.name}',
            tags=['datasets'],
        )
    return api_router
