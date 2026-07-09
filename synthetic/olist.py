"""Simulação das tabelas do Olist (Faker) e carga em massa via COPY.

Alimenta o RDS de origem da camada fria — pela Lambda de bootstrap
(``src/cold/bootstrap_db/handler.py``) ou pelo CLI
``scripts/database/seed_synthetic.py``.

O vocabulário abaixo (categorias, UFs, tipos de pagamento) é a **fonte única**
também dos eventos da camada quente (``synthetic/events.py``): é o que permite
a um ETL futuro unir as duas camadas com domínios compatíveis.

Geração pura, separada do I/O: as funções ``gen_*`` só devolvem tuplas; quem
fala com o Postgres é ``copy_rows``/``load``.
"""
from __future__ import annotations

import random
import uuid
from datetime import timedelta

from faker import Faker

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


def seed_random(seed: int) -> None:
    """Fixa as sementes (reprodutibilidade em teste e em lab)."""
    random.seed(seed)
    Faker.seed(seed)


def _new_id() -> str:
    """Id no formato de uuid4 hex, porém derivado do RNG do módulo.

    ``uuid.uuid4()`` lê de ``os.urandom`` e ignora ``random.seed()``, o que
    quebraria a reprodutibilidade prometida por ``seed_random``/``--seed``.
    """
    return uuid.UUID(int=random.getrandbits(128), version=4).hex


def _zip_prefix() -> str:
    return str(fake.random_int(10000, 99999))


def gen_customers(n: int) -> list[tuple]:
    """Clientes: customer_id único + customer_unique_id (a pessoa por trás)."""
    return [
        (
            _new_id(),
            _new_id(),
            _zip_prefix(),
            fake.city(),
            random.choice(CUSTOMER_STATES),
        )
        for _ in range(n)
    ]


def gen_sellers(n: int) -> list[tuple]:
    return [
        (_new_id(), _zip_prefix(), fake.city(), random.choice(CUSTOMER_STATES))
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
    return [
        (
            _new_id(),
            random.choice(list(PRODUCT_CATEGORIES)),
            random.randint(20, 60),
            random.randint(100, 3000),
            random.randint(1, 6),
            random.randint(100, 30000),
            random.randint(5, 100),
            random.randint(5, 100),
            random.randint(5, 100),
        )
        for _ in range(n)
    ]


def gen_order_graph(
    order_count: int,
    customer_ids: list[str],
    product_ids: list[str],
    seller_ids: list[str],
) -> dict[str, list[tuple]]:
    """Pedidos + itens + pagamentos + reviews coerentes entre si (FKs válidas)."""
    orders, items, payments, reviews = [], [], [], []
    for _ in range(order_count):
        order_id = _new_id()
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
                _new_id(),
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


# Colunas de cada tabela, na ordem em que as tuplas acima são geradas.
COLUMNS = {
    'product_category_name_translation': [
        'product_category_name',
        'product_category_name_english',
    ],
    'customers': [
        'customer_id',
        'customer_unique_id',
        'customer_zip_code_prefix',
        'customer_city',
        'customer_state',
    ],
    'sellers': [
        'seller_id',
        'seller_zip_code_prefix',
        'seller_city',
        'seller_state',
    ],
    'geolocation': [
        'geolocation_zip_code_prefix',
        'geolocation_lat',
        'geolocation_lng',
        'geolocation_city',
        'geolocation_state',
    ],
    'products': [
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
    'orders': [
        'order_id',
        'customer_id',
        'order_status',
        'order_purchase_timestamp',
        'order_approved_at',
        'order_delivered_carrier_date',
        'order_delivered_customer_date',
        'order_estimated_delivery_date',
    ],
    'order_items': [
        'order_id',
        'order_item_id',
        'product_id',
        'seller_id',
        'shipping_limit_date',
        'price',
        'freight_value',
    ],
    'order_payments': [
        'order_id',
        'payment_sequential',
        'payment_type',
        'payment_installments',
        'payment_value',
    ],
    'order_reviews': [
        'review_id',
        'order_id',
        'review_score',
        'review_comment_title',
        'review_comment_message',
        'review_creation_date',
        'review_answer_timestamp',
    ],
}

DEFAULT_SIZES = {
    'customers': 2000,
    'sellers': 200,
    'products': 1000,
    'geolocation': 1000,
    'orders': 5000,
}


def build_dataset(sizes: dict[str, int]) -> dict[str, list[tuple]]:
    """Gera todas as tabelas já na ordem de carga (dimensões antes dos fatos)."""
    customers = gen_customers(sizes['customers'])
    sellers = gen_sellers(sizes['sellers'])
    products = gen_products(sizes['products'])
    graph = gen_order_graph(
        sizes['orders'],
        [row[0] for row in customers],
        [row[0] for row in products],
        [row[0] for row in sellers],
    )
    return {
        'product_category_name_translation': list(PRODUCT_CATEGORIES.items()),
        'customers': customers,
        'sellers': sellers,
        'geolocation': gen_geolocation(sizes['geolocation']),
        'products': products,
        **graph,
    }


def copy_rows(cursor, table: str, rows: list[tuple]) -> None:
    """Carga em massa via COPY (ordens de magnitude mais rápida que INSERT)."""
    columns = ', '.join(COLUMNS[table])
    with cursor.copy(f'COPY olist.{table} ({columns}) FROM STDIN') as copy:
        for row in rows:
            copy.write_row(row)


def already_seeded(cursor) -> bool:
    """Idempotência: se já há pedidos, não recarrega nada."""
    cursor.execute('SELECT count(*) FROM olist.orders')
    return cursor.fetchone()[0] > 0


def load(cursor, sizes: dict[str, int]) -> dict[str, int]:
    """Carrega o dataset inteiro; retorna a contagem por tabela."""
    dataset = build_dataset(sizes)
    for table in COLUMNS:
        copy_rows(cursor, table, dataset[table])
    return {table: len(rows) for table, rows in dataset.items()}
