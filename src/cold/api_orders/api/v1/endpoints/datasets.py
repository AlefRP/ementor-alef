"""Endpoints genéricos dos datasets Olist — snapshot resumível por keyset de PK.

``/v1/orders`` continua incremental pelo timestamp de compra; as demais tabelas
não têm coluna de evento monotônica, então o contrato aqui é um scan estável
ordenado pela chave primária: o cliente repete ``after`` (um valor por coluna
da chave) até receber ``items`` vazio. ``next_cursor`` vem sempre que há itens
— mesmo em página parcial — para a ingestão retomar sem reler a última página.

Cache-aside (fastapi-cache2): a resposta é cacheada por URL (path + query) com
TTL curto; um hit devolve a página sem tocar o RDS. Ver ``core/configs.py``.
"""
from dataclasses import dataclass
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi_cache.decorator import cache
from pydantic import BaseModel

from src.cold.api_orders.core.configs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.cold.api_orders.core.deps import get_connection
from src.cold.api_orders.schemas.dataset_schema import (
    CategoryTranslation,
    Customer,
    DatasetPage,
    Geolocation,
    OrderItem,
    OrderPayment,
    OrderReview,
    Product,
    Seller,
)


@dataclass(frozen=True)
class DatasetSpec:
    """Como servir uma tabela: rota (= tabela e dataset na raw) e keyset."""

    name: str
    key_columns: tuple[str, ...]
    key_casts: tuple[str, ...]
    model: type[BaseModel]


SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec('customers', ('customer_id',), ('text',), Customer),
    DatasetSpec('sellers', ('seller_id',), ('text',), Seller),
    DatasetSpec('products', ('product_id',), ('text',), Product),
    DatasetSpec('geolocation', ('geolocation_id',), ('bigint',), Geolocation),
    DatasetSpec(
        'product_category_name_translation',
        ('product_category_name',),
        ('text',),
        CategoryTranslation,
    ),
    DatasetSpec(
        'order_items',
        ('order_id', 'order_item_id'),
        ('text', 'integer'),
        OrderItem,
    ),
    DatasetSpec(
        'order_payments',
        ('order_id', 'payment_sequential'),
        ('text', 'integer'),
        OrderPayment,
    ),
    DatasetSpec(
        'order_reviews',
        ('review_id', 'order_id'),
        ('text', 'text'),
        OrderReview,
    ),
)


def _select_sql(spec: DatasetSpec, with_cursor: bool) -> str:
    """SQL montado só de metadados do spec — nunca de input do cliente."""
    columns = ', '.join(spec.model.model_fields)
    keys = ', '.join(spec.key_columns)
    where = ''
    if with_cursor:
        # Valores do cursor chegam como texto; o cast devolve o tipo da PK.
        placeholders = ', '.join(
            f'%(key{i})s::{cast}' for i, cast in enumerate(spec.key_casts)
        )
        where = f' WHERE ({keys}) > ({placeholders})'
    # B608 suprimido: identificadores vêm APENAS do registro SPECS (literais
    # deste módulo); valores do cliente entram como parâmetros do psycopg.
    return (
        f'SELECT {columns} FROM olist.{spec.name}{where}'  # nosec B608
        f' ORDER BY {keys} LIMIT %(page_size)s'
    )


def _url_key_builder(
    func, namespace='', *, request=None, response=None, args=(), kwargs=None
):
    """Chave por URL completa: única por dataset, cursor e tamanho de página.

    O default do fastapi-cache2 usa ``repr`` dos argumentos — a conexão do pool
    entraria na chave e nunca haveria hit; a URL identifica a página exata.
    """
    return f'{namespace}:{request.url.path}?{request.url.query}'


def build_router(spec: DatasetSpec, cache_ttl: int) -> APIRouter:
    """Router do dataset; com cache-aside quando ``cache_ttl > 0``."""
    router = APIRouter()
    page_model = DatasetPage[spec.model]
    sql_first = _select_sql(spec, with_cursor=False)
    sql_after = _select_sql(spec, with_cursor=True)

    async def list_rows(
        request: Request,
        conn: Annotated[psycopg.AsyncConnection, Depends(get_connection)],
        after: Annotated[list[str] | None, Query()] = None,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ):
        """Linhas após o cursor ``after``, em ordem estável de chave primária.

        O consumidor repete a chamada ecoando o ``next_cursor`` recebido até
        ``items`` vir vazio.
        """
        cursor_values = list(after or [])
        if cursor_values and len(cursor_values) != len(spec.key_columns):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f'after deve ter {len(spec.key_columns)} valor(es), na'
                    f' ordem: {", ".join(spec.key_columns)}'
                ),
            )
        params: dict = {'page_size': page_size}
        for i, value in enumerate(cursor_values):
            params[f'key{i}'] = value
        sql = sql_after if cursor_values else sql_first
        db_cursor = await conn.execute(sql, params)
        rows = await db_cursor.fetchall()
        items = [spec.model(**row) for row in rows]
        next_cursor = None
        if items:
            last = items[-1]
            next_cursor = [str(getattr(last, col)) for col in spec.key_columns]
        return page_model(items=items, next_cursor=next_cursor)

    if cache_ttl > 0:
        list_rows = cache(expire=cache_ttl, key_builder=_url_key_builder)(list_rows)

    router.get('', response_model=page_model)(list_rows)
    return router
