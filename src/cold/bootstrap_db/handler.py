"""Lambda de bootstrap do banco de origem (camada fria).

Existe porque o RDS é 100% privado (sem NAT, sem SSM) e a EC2 da API não
alcança o Secrets Manager: só o gateway endpoint de S3 é gratuito. Esta função
roda DENTRO da VPC — logo enxerga o RDS pelo security group — e recebe a senha
do master via variável de ambiente (cifrada em repouso pelo KMS da Lambda),
lida pelo Terraform do secret gerenciado do RDS no apply.

Faz o bootstrap completo e **idempotente**:
1. aplica o schema (``olist_schema.sql``);
2. semeia dados sintéticos (Faker) se ``olist.orders`` estiver vazia;
3. cria o usuário ``api_reader`` com IAM auth (``create_api_reader.sql``).

Rodar de novo é seguro: o schema usa IF NOT EXISTS, o seed sai cedo se já há
pedidos e o create_api_reader é um DO $$ guardado.
"""
import json
import logging
import os
from pathlib import Path

import psycopg

from synthetic import olist

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SQL_DIR = Path(__file__).parent


def _config() -> dict:
    """Lê a configuração do ambiente a cada invocação (testável)."""
    return {
        'host': os.environ['PGHOST'],
        'port': int(os.environ.get('PGPORT', '5432')),
        'dbname': os.environ.get('PGDATABASE', 'olist'),
        'user': os.environ.get('PGUSER', 'lakehouse_admin'),
        'password': os.environ['PGPASSWORD'],
        'sizes': {
            key: int(os.environ.get(f'SEED_{key.upper()}', default))
            for key, default in olist.DEFAULT_SIZES.items()
        },
    }


def _run_sql_file(cursor, name: str) -> None:
    cursor.execute(SQL_DIR.joinpath(name).read_text(encoding='utf-8'))


def handler(event, context):
    """Aplica schema, semeia (uma vez) e cria o usuário de leitura da API."""
    config = _config()
    try:
        with psycopg.connect(
            host=config['host'],
            port=config['port'],
            dbname=config['dbname'],
            user=config['user'],
            password=config['password'],
        ) as conn:
            with conn.cursor() as cursor:
                _run_sql_file(cursor, 'olist_schema.sql')
                conn.commit()

                seeded = olist.already_seeded(cursor)
                counts = {} if seeded else olist.load(cursor, config['sizes'])
                conn.commit()

                # Depois do seed: o GRANT SELECT precisa das tabelas existindo.
                _run_sql_file(cursor, 'create_api_reader.sql')
                conn.commit()
        logger.info(
            json.dumps(
                {
                    'event': 'bootstrap_ok',
                    'already_seeded': seeded,
                    'rows': counts,
                }
            )
        )
        return {'statusCode': 200, 'already_seeded': seeded, 'rows': counts}
    except Exception:
        logger.exception(json.dumps({'event': 'bootstrap_error'}))
        raise
