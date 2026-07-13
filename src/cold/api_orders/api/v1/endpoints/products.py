"""Rota da tabela ``olist.products``."""
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Query

from src.cold.api_orders.api.v1.endpoints._tables import (
    DatasetSpec,
    cache_de_rota,
    listar_linhas_da_tabela,
)
from src.cold.api_orders.core.configs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.cold.api_orders.core.deps import obter_conexao
from src.cold.api_orders.schemas.dataset_schema import DatasetPage, Product

router = APIRouter()

SPEC = DatasetSpec('products', ('product_id',), ('text',), Product)


@router.get(
    '',
    operation_id='list_products',
    summary='Lista products',
)
@cache_de_rota
async def listar_products(
    conn: Annotated[psycopg.AsyncConnection, Depends(obter_conexao)],
    after: Annotated[list[str] | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DatasetPage[Product]:
    """Linhas de ``olist.products`` após o cursor ``after``."""
    return await listar_linhas_da_tabela(
        spec=SPEC,
        conn=conn,
        after=after,
        page_size=page_size,
    )
