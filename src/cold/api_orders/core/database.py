"""Pool assíncrono de conexões (psycopg_pool) com o RDS PostgreSQL.

Dois modos de autenticação (``DB_AUTH``): ``password`` (dev/testes) e ``iam``
— token do RDS assinado localmente pela role da EC2 (SigV4, sem chamada de
rede e sem segredo em runtime). O token vale 15 minutos, por isso o modo iam
usa um pool que o renova a cada conexão nova.
"""
import json

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.cold.api_orders.core.configs import Settings


def resolve_password(settings: Settings) -> str:
    """Senha do RDS: ambiente (dev) ou Secrets Manager (fallback)."""
    if settings.PGPASSWORD:
        return settings.PGPASSWORD
    if settings.SECRET_ARN:
        import boto3  # import tardio: só o caminho com SECRET_ARN usa boto3

        client = boto3.client('secretsmanager')
        payload = client.get_secret_value(SecretId=settings.SECRET_ARN)
        return json.loads(payload['SecretString'])['password']
    return ''


def iam_auth_token(settings: Settings) -> str:
    """Token IAM do RDS (15 min), assinado localmente — sem rede."""
    import boto3  # import tardio: só o modo iam usa boto3

    client = boto3.client('rds')
    return client.generate_db_auth_token(
        DBHostname=settings.PGHOST,
        Port=settings.PGPORT,
        DBUsername=settings.PGUSER,
    )


class IamAuthPool(AsyncConnectionPool):
    """Pool que renova o token IAM a cada conexão nova (TTL de 15 min)."""

    def __init__(self, *args, settings: Settings, **kwargs):
        self._settings = settings
        super().__init__(*args, **kwargs)

    async def _connect(self, timeout=None):
        self.kwargs['password'] = iam_auth_token(self._settings)
        return await super()._connect(timeout=timeout)


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """Cria o pool fechado; o lifespan da aplicação faz open/close."""
    conninfo = (
        f'host={settings.PGHOST} port={settings.PGPORT} '
        f'dbname={settings.PGDATABASE} user={settings.PGUSER}'
    )
    common = {
        'kwargs': {'row_factory': dict_row},
        'min_size': settings.POOL_MIN_SIZE,
        'max_size': settings.POOL_MAX_SIZE,
        'open': False,
    }
    if settings.DB_AUTH == 'iam':
        # IAM auth exige TLS; o token entra como senha a cada conexão.
        return IamAuthPool(
            conninfo=f'{conninfo} sslmode=require',
            settings=settings,
            **common,
        )
    common['kwargs']['password'] = resolve_password(settings)
    return AsyncConnectionPool(conninfo=conninfo, **common)
