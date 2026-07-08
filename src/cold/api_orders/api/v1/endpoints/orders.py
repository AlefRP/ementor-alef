"""Endpoint de pedidos — extração incremental com paginação keyset.

A ordenação estável por ``(order_purchase_timestamp, order_id)`` usa o índice
``idx_orders_purchase_ts`` criado no seed; ``LIMIT`` + tupla no ``WHERE``
evitam o custo crescente de ``OFFSET`` em extrações longas.
"""
from datetime import datetime
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Query

from src.cold.api_orders.core.configs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.cold.api_orders.core.deps import get_connection
from src.cold.api_orders.schemas.order_schema import Order, OrdersPage, PageCursor

router = APIRouter()

KEYSET_START = datetime(1900, 1, 1)

_ORDERS_SQL = """
    SELECT order_id,
           customer_id,
           order_status,
           order_purchase_timestamp,
           order_approved_at,
           order_delivered_carrier_date,
           order_delivered_customer_date,
           order_estimated_delivery_date
      FROM olist.orders
     WHERE (order_purchase_timestamp, order_id)
           > (%(purchased_after)s, %(after_id)s)
     ORDER BY order_purchase_timestamp, order_id
     LIMIT %(page_size)s
"""


@router.get('', response_model=OrdersPage)
async def list_orders(
    conn: Annotated[psycopg.AsyncConnection, Depends(get_connection)],
    purchased_after: datetime = KEYSET_START,
    after_id: str = '',
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> OrdersPage:
    """Pedidos após o cursor ``(purchased_after, after_id)``, em ordem estável.

    O consumidor repete a chamada com o ``next_cursor`` retornado até ele vir
    ``null``. Pedidos sem ``order_purchase_timestamp`` ficam fora do keyset.
    """
    cursor = await conn.execute(
        _ORDERS_SQL,
        {
            'purchased_after': purchased_after,
            'after_id': after_id,
            'page_size': page_size,
        },
    )
    rows = await cursor.fetchall()
    items = [Order(**row) for row in rows]
    next_cursor = None
    if len(items) == page_size:
        last = items[-1]
        next_cursor = PageCursor(
            purchased_after=last.order_purchase_timestamp,
            after_id=last.order_id,
        )
    return OrdersPage(items=items, next_cursor=next_cursor)
