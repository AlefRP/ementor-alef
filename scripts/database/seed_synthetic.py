#!/usr/bin/env python3
"""CLI do seed SINTÉTICO do Olist (Faker) — alternativa à carga dos CSVs reais
(``seed_olist.sh``) quando se quer volume controlável e independência de fonte
externa.

A simulação dos dados vive em ``simulation/olist.py`` (compartilhada com a Lambda
de bootstrap, que é o caminho usado quando o RDS é privado). Este script é o
atalho para quem JÁ tem rota de rede até o banco (bastion ou túnel).

Idempotente: se ``olist.orders`` já tem linhas, encerra sem tocar em nada.

Uso:
    PGHOST=<endpoint> PGDATABASE=olist PGUSER=lakehouse_admin \\
    SECRET_ARN=<arn do secret do RDS> \\
    python scripts/database/seed_synthetic.py --orders 5000

    (alternativa sem awscli: exporte PGPASSWORD diretamente)

Requisitos: pip install 'psycopg[binary]' faker
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulation import olist  # noqa: E402

SCHEMA_SQL = Path(__file__).parent / 'olist_schema.sql'


def _resolve_password() -> str:
    """Senha via PGPASSWORD ou Secrets Manager (mesma lógica do seed_olist.sh)."""
    if os.environ.get('PGPASSWORD'):
        return os.environ['PGPASSWORD']
    secret_arn = os.environ.get('SECRET_ARN')
    if not secret_arn:
        sys.exit('Defina PGPASSWORD ou SECRET_ARN (secret do RDS).')
    raw = subprocess.check_output(
        [
            'aws',
            'secretsmanager',
            'get-secret-value',
            '--secret-id',
            secret_arn,
            '--query',
            'SecretString',
            '--output',
            'text',
        ]
    )
    return json.loads(raw)['password']


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Seed sintético do Olist (Faker).')
    for table, default in olist.DEFAULT_SIZES.items():
        parser.add_argument(f'--{table}', type=int, default=default)
    parser.add_argument('--seed', type=int, default=None, help='reprodutibilidade')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.seed is not None:
        olist.seed_random(args.seed)
    sizes = {table: getattr(args, table) for table in olist.DEFAULT_SIZES}

    with psycopg.connect(
        host=os.environ['PGHOST'],
        port=int(os.environ.get('PGPORT', '5432')),
        dbname=os.environ.get('PGDATABASE', 'olist'),
        user=os.environ.get('PGUSER', 'lakehouse_admin'),
        password=_resolve_password(),
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(SCHEMA_SQL.read_text(encoding='utf-8'))
            conn.commit()
            if olist.already_seeded(cursor):
                print('>> olist.orders já possui dados — nada a fazer.')
                return 0
            counts = olist.load(cursor, sizes)
            conn.commit()

    print('>> Seed sintético concluído:')
    for table, count in counts.items():
        print(f'   {table}: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
