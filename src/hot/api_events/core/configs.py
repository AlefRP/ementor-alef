"""Configurações da Event API (pydantic-settings, lidas do ambiente/.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Limite de entradas do send_message_batch — imposto pela API do SQS.
SQS_BATCH_MAX = 10

# Teto de eventos por requisição (50 lotes de 10). Protege a instância de um
# request gigante: o produtor pagina, em vez de mandar tudo de uma vez.
MAX_EVENTS_POR_REQUISICAO = 500


class Settings(BaseSettings):
    """Parâmetros da aplicação e da fila de destino (camada quente)."""

    PROJECT_NAME: str = 'Olist Event API'
    API_V1_STR: str = '/v1'

    # URL da fila de eventos; injetada pelo user_data da EC2 (módulo api_ec2).
    QUEUE_URL: str = ''

    # Defesa em profundidade: se definido, o v1 exige o header x-api-token.
    API_TOKEN: str = ''

    model_config = SettingsConfigDict(
        env_file='.env', case_sensitive=True, extra='ignore'
    )


@lru_cache(maxsize=1)
def obter_configuracoes() -> Settings:
    """Instância única de Settings (testes limpam com ``cache_clear``)."""
    return Settings()
