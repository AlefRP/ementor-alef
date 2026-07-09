#!/usr/bin/env python3
"""Seed SINTÉTICO do banco de origem (Olist) via Faker — alternativa à carga
dos CSVs reais (seed_olist.sh) quando se quer volume controlável, dados
"frescos" e independência de fonte externa.

Gera as 9 tabelas do schema `olist` com integridade referencial (dimensões
antes de fatos) e vocabulário consistente com os eventos da camada quente
(mesmas categorias/UFs/tipos de pagamento) — assim um ETL raw->silver->gold
que junta as camadas fria e quente faz sentido.

Idempotente: se `olist.orders` já tem linhas, encerra sem tocar em nada.

Uso:
    PGHOST=<endpoint> PGDATABASE=olist PGUSER=lakehouse_admin \\
    SECRET_ARN=<arn do secret do RDS> \\
    python scripts/database/seed_synthetic.py --orders 5000

    (alternativa sem awscli: exporte PGPASSWORD diretamente)

Requisitos: psycopg[binary] e faker (pip install 'psycopg[binary]' faker).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
from faker import Faker

# Vocabulário compartilhado com o producer da camada quente
# (src/hot/event_producer/handler.py) — manter os dois em sincronia.
PRODUCT_CATEGORIES = {
    'cama_mesa_banho': 'bed_bath_table',
    'beleza_saude': 'health_beauty',
    'esporte_lazer': 'sports_leisure',
    'moveis_decoracao': 'furniture_decor',
    'informatica_acessorios': 'computers_accessories',
    'utilidades_domesticas': 'housewares',
    'relogios_presentes': 'watches_gifts',
    'telefonia': 'telephony',
    'brinquedos': 'toys',
    'automotivo': 'auto',
}
CUSTOMER_STATES = ('SP', 'RJ', 'MG', 'RS', 'PR', 'SC', 'BA', 'DF', 'GO', 'ES')
PAYMENT_TYPES = ('credit_card', 'boleto', 'voucher', 'debit_card', 'pix')
ORDER_STATUSES = ('delivered', 'shipped', 'invoiced', 'approved', 'canceled')

fake = Faker('pt_BR')


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


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ['PGHOST'],
        port=int(os.environ.get('PGPORT', '5432')),
        dbname=os.environ.get('PGDATABASE', 'olist'),
        user=os.environ.get('PGUSER', 'lakehouse_admin'),
        password=_resolve_password(),
    )


def _zip_prefix() -> str:
    return f'{fake.random_int(10000, 99999)}'[:5]


def gen_customers(n: int) -> list[tuple]:
    """Dimensão de clientes: id único + unique_id (mesma pessoa, vários pedidos)."""
    rows = []
    for _ in range(n):
        rows.append(
            (
                uuid.uuid4().hex,
                uuid.uuid4().hex,
                _zip_prefix(),
                fake.city(),
                random.choice(CUSTOMER_STATES),
            )
        )
    return rows


def gen_sellers(n: int) -> list[tuple]:
    return [
        (uuid.uuid4().hex, _zip_prefix(), fake.city(), random.choice(CUSTOMER_STATES))
        for _ in range(n)
    ]


def gen_geolocation(n: int) -> list[tuple]:
    return [
        (
            _zip_prefix(),
            float(fake.latitude()),
            float(fake.longitude()),
            fake.city(),
            random.choice(CUSTOMER_STATES),
        )
        for _ in range(n)
    ]


def gen_products(n: int) -> list[tuple]:
    rows = []
    for _ in range(n):
        rows.append(
            (
                uuid.uuid4().hex,
                random.choice(list(PRODUCT_CATEGORIES)),
                random.randint(20, 60),
                random.randint(100, 3000),
                random.randint(1, 6),
                random.randint(100, 30000),
                random.randint(5, 100),
                random.randint(5, 100),
                random.randint(5, 100),
            )
        )
    return rows


def gen_order_graph(
    order_count: int,
    customer_ids: list[str],
    product_ids: list[str],
    seller_ids: list[str],
) -> dict[str, list[tuple]]:
    """Gera pedidos + itens + pagamentos + reviews coerentes entre si (FKs)."""
    orders, items, payments, reviews = [], [], [], []
    for _ in range(order_count):
        order_id = uuid.uuid4().hex
        purchased = fake.date_time_between(start_date='-2y', end_date='now')
        approved = purchased + timedelta(hours=random.randint(1, 48))
        delivered = approved + timedelta(days=random.randint(1, 20))
        estimated = purchased + timedelta(days=random.randint(5, 30))
        orders.append(
            (
                order_id,
                random.choice(customer_ids),
                random.choice(ORDER_STATUSES),
                purchased,
                approved,
                approved + timedelta(days=random.randint(1, 5)),
                delivered,
                estimated,
            )
        )
        for item_id in range(1, random.randint(1, 4) + 1):
            items.append(
                (
                    order_id,
                    item_id,
                    random.choice(product_ids),
                    random.choice(seller_ids),
                    approved,
                    round(random.uniform(15.0, 800.0), 2),
                    round(random.uniform(5.0, 60.0), 2),
                )
            )
        payments.append(
            (
                order_id,
                1,
                random.choice(PAYMENT_TYPES),
                random.randint(1, 10),
                round(random.uniform(20.0, 900.0), 2),
            )
        )
        reviews.append(
            (
                uuid.uuid4().hex,
                order_id,
                random.randint(1, 5),
                None,
                fake.sentence(nb_words=8),
                delivered,
                delivered + timedelta(days=random.randint(1, 3)),
            )
        )
    return {
        'orders': orders,
        'order_items': items,
        'order_payments': payments,
        'order_reviews': reviews,
    }


def _copy(cur: psycopg.Cursor, table: str, columns: list[str], rows: list[tuple]):
    """Carga em massa via COPY (muito mais rápido que INSERT por linha)."""
    cols = ', '.join(columns)
    with cur.copy(f'COPY olist.{table} ({cols}) FROM STDIN') as copy:
        for row in rows:
            copy.write_row(row)


def seed(conn: psycopg.Connection, sizes: dict[str, int]) -> dict[str, int]:
    """Popula todas as tabelas em uma transação; retorna a contagem por tabela."""
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM olist.orders')
        if cur.fetchone()[0] > 0:
            print('>> olist.orders já possui dados — nada a fazer (carga é única).')
            return {}

        _copy(
            cur,
            'product_category_name_translation',
            ['product_category_name', 'product_category_name_english'],
            list(PRODUCT_CATEGORIES.items()),
        )
        customers = gen_customers(sizes['customers'])
        sellers = gen_sellers(sizes['sellers'])
        products = gen_products(sizes['products'])
        _copy(
            cur,
            'customers',
            [
                'customer_id',
                'customer_unique_id',
                'customer_zip_code_prefix',
                'customer_city',
                'customer_state',
            ],
            customers,
        )
        _copy(
            cur,
            'sellers',
            ['seller_id', 'seller_zip_code_prefix', 'seller_city', 'seller_state'],
            sellers,
        )
        _copy(
            cur,
            'geolocation',
            [
                'geolocation_zip_code_prefix',
                'geolocation_lat',
                'geolocation_lng',
                'geolocation_city',
                'geolocation_state',
            ],
            gen_geolocation(sizes['geolocation']),
        )
        _copy(
            cur,
            'products',
            [
                'product_id',
                'product_category_name',
                'product_name_lenght',
                'product_description_lenght',
                'product_photos_qty',
                'product_weight_g',
                'product_length_cm',
                'product_height_cm',
                'product_width_cm',
            ],
            products,
        )
        graph = gen_order_graph(
            sizes['orders'],
            [c[0] for c in customers],
            [p[0] for p in products],
            [s[0] for s in sellers],
        )
        _copy(
            cur,
            'orders',
            [
                'order_id',
                'customer_id',
                'order_status',
                'order_purchase_timestamp',
                'order_approved_at',
                'order_delivered_carrier_date',
                'order_delivered_customer_date',
                'order_estimated_delivery_date',
            ],
            graph['orders'],
        )
        _copy(
            cur,
            'order_items',
            [
                'order_id',
                'order_item_id',
                'product_id',
                'seller_id',
                'shipping_limit_date',
                'price',
                'freight_value',
            ],
            graph['order_items'],
        )
        _copy(
            cur,
            'order_payments',
            [
                'order_id',
                'payment_sequential',
                'payment_type',
                'payment_installments',
                'payment_value',
            ],
            graph['order_payments'],
        )
        _copy(
            cur,
            'order_reviews',
            [
                'review_id',
                'order_id',
                'review_score',
                'review_comment_title',
                'review_comment_message',
                'review_creation_date',
                'review_answer_timestamp',
            ],
            graph['order_reviews'],
        )
    conn.commit()
    return {
        'customers': len(customers),
        'sellers': len(sellers),
        'products': len(products),
        'orders': len(graph['orders']),
        'order_items': len(graph['order_items']),
        'order_payments': len(graph['order_payments']),
        'order_reviews': len(graph['order_reviews']),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Seed sintético do Olist (Faker).')
    parser.add_argument('--orders', type=int, default=5000)
    parser.add_argument('--customers', type=int, default=2000)
    parser.add_argument('--sellers', type=int, default=200)
    parser.add_argument('--products', type=int, default=1000)
    parser.add_argument('--geolocation', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=None, help='semente p/ reprodutibilidade')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)
    sizes = {
        'orders': args.orders,
        'customers': args.customers,
        'sellers': args.sellers,
        'products': args.products,
        'geolocation': args.geolocation,
    }
    schema_sql = (Path(__file__).parent / 'olist_schema.sql').read_text(encoding='utf-8')
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        counts = seed(conn, sizes)
    if counts:
        print('>> Seed sintético concluído:')
        for table, count in counts.items():
            print(f'   {table}: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
