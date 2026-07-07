"""Configurações da API fria (pydantic-settings, lidas do ambiente/.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 1000


class Settings(BaseSettings):
    """Parâmetros da aplicação e da conexão com o RDS (Olist)."""

    PROJECT_NAME: str = 'Olist Data Product API'
    API_V1_STR: str = '/v1'

    PGHOST: str = 'localhost'
    PGPORT: int = 5432
    PGDATABASE: str = 'olist'
    PGUSER: str = 'lakehouse_admin'
    # Senha direta (dev/testes) OU secret do RDS (EC2 com instance profile).
    PGPASSWORD: str = ''
    SECRET_ARN: str = ''

    POOL_MIN_SIZE: int = 1
    POOL_MAX_SIZE: int = 10

    # Defesa em profundidade: se definido, o v1 exige o header x-api-token.
    API_TOKEN: str = ''

    model_config = SettingsConfigDict(
        env_file='.env', case_sensitive=True, extra='ignore'
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instância única de Settings (testes limpam com ``cache_clear``)."""
    return Settings()
