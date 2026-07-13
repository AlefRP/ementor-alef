"""Helper interno para rotas de tabelas Olist com paginação por PK."""
from dataclasses import dataclass

import psycopg
from fastapi import HTTPException, status
from fastapi_cache.decorator import cache
from pydantic import BaseModel

from src.cold.api_orders.schemas.dataset_schema import DatasetPage


@dataclass(frozen=True)
class DatasetSpec:
    """Como servir uma tabela: rota (= tabela e dataset na raw) e keyset."""

    name: str
    key_columns: tuple[str, ...]
    key_casts: tuple[str, ...]
    model: type[BaseModel]


def _construir_chave_por_url(
    func, namespace='', *, request=None, response=None, args=(), kwargs=None
):
    """Chave por URL completa: unica por tabela, cursor e tamanho de pagina."""
    return f'{namespace}:{request.url.path}?{request.url.query}'


cache_de_rota = cache(key_builder=_construir_chave_por_url)


def _montar_sql_select(spec: DatasetSpec, with_cursor: bool) -> str:
    """SQL montado só de metadados do spec - nunca de input do cliente."""
    columns = ', '.join(spec.model.model_fields)
    keys = ', '.join(spec.key_columns)
    where = ''
    if with_cursor:
        placeholders = ', '.join(
            f'%(key{i})s::{cast}' for i, cast in enumerate(spec.key_casts)
        )
        where = f' WHERE ({keys}) > ({placeholders})'
    return (
        f'SELECT {columns} FROM olist.{spec.name}{where}'  # nosec B608
        f' ORDER BY {keys} LIMIT %(page_size)s'
    )


async def listar_linhas_da_tabela(
    *,
    spec: DatasetSpec,
    conn: psycopg.AsyncConnection,
    after: list[str] | None,
    page_size: int,
):
    """Lista uma página de uma tabela por cursor de chave primária."""

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

    sql = _montar_sql_select(spec, with_cursor=bool(cursor_values))
    db_cursor = await conn.execute(sql, params)
    rows = await db_cursor.fetchall()
    items = [spec.model(**row) for row in rows]
    next_cursor = None
    if items:
        last = items[-1]
        next_cursor = [str(getattr(last, col)) for col in spec.key_columns]

    page_model = DatasetPage[spec.model]
    page = page_model(items=items, next_cursor=next_cursor)
    return page
