"""Rota da tabela ``olist.product_category_name_translation``."""
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
from src.cold.api_orders.schemas.dataset_schema import CategoryTranslation, DatasetPage

router = APIRouter()

SPEC = DatasetSpec(
    'product_category_name_translation',
    ('product_category_name',),
    ('text',),
    CategoryTranslation,
)


@router.get(
    '',
    operation_id='list_product_category_name_translation',
    summary='Lista product_category_name_translation',
)
@cache_de_rota
async def listar_product_category_name_translation(
    conn: Annotated[psycopg.AsyncConnection, Depends(obter_conexao)],
    after: Annotated[list[str] | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DatasetPage[CategoryTranslation]:
    """Linhas de ``olist.product_category_name_translation`` após o cursor ``after``."""
    return await listar_linhas_da_tabela(
        spec=SPEC,
        conn=conn,
        after=after,
        page_size=page_size,
    )
