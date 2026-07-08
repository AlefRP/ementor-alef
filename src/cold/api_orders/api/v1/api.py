"""Agregador de rotas da versão 1 da API."""
from fastapi import APIRouter

from src.cold.api_orders.api.v1.endpoints import orders

api_router = APIRouter()
api_router.include_router(orders.router, prefix='/orders', tags=['orders'])
