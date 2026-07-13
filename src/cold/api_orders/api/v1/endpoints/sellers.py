"""Rota da tabela ``olist.sellers``."""
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Query, Request

from src.cold.api_orders.api.v1.endpoints._tables import (
    DatasetSpec,
    cache_de_rota,
    listar_linhas_da_tabela,
)
from src.cold.api_orders.core.configs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.cold.api_orders.core.deps import obter_conexao
from src.cold.api_orders.schemas.dataset_schema import DatasetPage, Seller

router = APIRouter()

SPEC = DatasetSpec('sellers', ('seller_id',), ('text',), Seller)


@router.get(
    '',
    operation_id='list_sellers',
    summary='Lista sellers',
)
@cache_de_rota
async def listar_sellers(
    request: Request,
    conn: Annotated[psycopg.AsyncConnection, Depends(obter_conexao)],
    after: Annotated[list[str] | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DatasetPage[Seller]:
    """Linhas de ``olist.sellers`` após o cursor ``after``."""
    return await listar_linhas_da_tabela(
        request=request,
        spec=SPEC,
        conn=conn,
        after=after,
        page_size=page_size,
    )
