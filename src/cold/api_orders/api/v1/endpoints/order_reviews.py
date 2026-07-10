"""Rota da tabela ``olist.order_reviews``."""
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Query, Request

from src.cold.api_orders.api.v1.endpoints._tables import (
    DatasetSpec,
    cache_table_route,
    list_table_rows,
)
from src.cold.api_orders.core.configs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.cold.api_orders.core.deps import get_connection
from src.cold.api_orders.schemas.dataset_schema import DatasetPage, OrderReview

router = APIRouter()

SPEC = DatasetSpec(
    'order_reviews',
    ('review_id', 'order_id'),
    ('text', 'text'),
    OrderReview,
)


@router.get(
    '',
    operation_id='list_order_reviews',
    summary='Lista order_reviews',
)
@cache_table_route
async def list_order_reviews(
    request: Request,
    conn: Annotated[psycopg.AsyncConnection, Depends(get_connection)],
    after: Annotated[list[str] | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DatasetPage[OrderReview]:
    """Linhas de ``olist.order_reviews`` após o cursor ``after``."""
    return await list_table_rows(
        request=request,
        spec=SPEC,
        conn=conn,
        after=after,
        page_size=page_size,
    )








