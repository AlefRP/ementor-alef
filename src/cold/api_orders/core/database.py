"""Pool assíncrono de conexões (psycopg_pool) com o RDS PostgreSQL."""
import json

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.cold.api_orders.core.configs import Settings


def resolve_password(settings: Settings) -> str:
    """Senha do RDS: ambiente (dev) ou Secrets Manager (EC2 com role)."""
    if settings.PGPASSWORD:
        return settings.PGPASSWORD
    if settings.SECRET_ARN:
        import boto3  # import tardio: só o caminho com SECRET_ARN usa boto3

        client = boto3.client('secretsmanager')
        payload = client.get_secret_value(SecretId=settings.SECRET_ARN)
        return json.loads(payload['SecretString'])['password']
    return ''


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """Cria o pool fechado; o lifespan da aplicação faz open/close."""
    conninfo = (
        f'host={settings.PGHOST} port={settings.PGPORT} '
        f'dbname={settings.PGDATABASE} user={settings.PGUSER}'
    )
    return AsyncConnectionPool(
        conninfo=conninfo,
        kwargs={
            'password': resolve_password(settings),
            'row_factory': dict_row,
        },
        min_size=settings.POOL_MIN_SIZE,
        max_size=settings.POOL_MAX_SIZE,
        open=False,
    )
