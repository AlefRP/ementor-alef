"""Agregador de rotas da versão 1 da API."""
from fastapi import APIRouter

from src.cold.api_orders.api.v1.endpoints import (
    customers,
    geolocation,
    order_items,
    order_payments,
    order_reviews,
    orders,
    product_category_name_translation,
    products,
    sellers,
)

_TABLE_ROUTERS = (
    (customers, '/customers', 'customers'),
    (sellers, '/sellers', 'sellers'),
    (products, '/products', 'products'),
    (geolocation, '/geolocation', 'geolocation'),
    (
        product_category_name_translation,
        '/product_category_name_translation',
        'product_category_name_translation',
    ),
    (order_items, '/order_items', 'order_items'),
    (order_payments, '/order_payments', 'order_payments'),
    (order_reviews, '/order_reviews', 'order_reviews'),
)


def montar_roteador_v1() -> APIRouter:
    """Monta o v1 por aplicação (o TTL do cache é decisão de configuração)."""
    api_router = APIRouter()
    api_router.include_router(orders.router, prefix='/orders', tags=['orders'])
    for module, prefix, tag in _TABLE_ROUTERS:
        api_router.include_router(
            module.router,
            prefix=prefix,
            tags=[tag],
        )
    return api_router
