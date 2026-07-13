"""Rota da tabela ``olist.geolocation``."""
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
from src.cold.api_orders.schemas.dataset_schema import DatasetPage, Geolocation

router = APIRouter()

SPEC = DatasetSpec('geolocation', ('geolocation_id',), ('bigint',), Geolocation)


@router.get(
    '',
    operation_id='list_geolocation',
    summary='Lista geolocation',
)
@cache_de_rota
async def listar_geolocation(
    conn: Annotated[psycopg.AsyncConnection, Depends(obter_conexao)],
    after: Annotated[list[str] | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DatasetPage[Geolocation]:
    """Linhas de ``olist.geolocation`` após o cursor ``after``."""
    return await listar_linhas_da_tabela(
        spec=SPEC,
        conn=conn,
        after=after,
        page_size=page_size,
    )
