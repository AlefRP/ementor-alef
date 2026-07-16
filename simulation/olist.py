"""Simulação das tabelas do Olist (Faker) e carga em massa via COPY.

Alimenta o RDS de origem da camada fria — pela Lambda de bootstrap
(``simulation/db_seeder/handler.py``) ou pelo CLI
``scripts/database/seed_synthetic.py``.

O vocabulário abaixo (categorias, UFs, tipos de pagamento) é a **fonte única**
também dos eventos da camada quente (``simulation/events.py``): é o que permite
a um ETL futuro unir as duas camadas com domínios compatíveis.

Geração pura, separada do I/O: as funções ``gerar_*`` só devolvem tuplas; quem
fala com o Postgres é ``copiar_linhas``/``carregar``.
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

# RNG próprio em vez do global do módulo ``random``: seedável (reprodutibilidade
# exige PRNG — ``secrets`` não aceita semente) e sem vazar estado para outros
# consumidores de ``random``. Dado sintético não é uso criptográfico.
_RNG = random.Random()  # nosec B311


def fixar_semente(semente: int) -> None:
    """Fixa as sementes (reprodutibilidade em teste e em lab)."""
    _RNG.seed(semente)
    Faker.seed(semente)


def _novo_id() -> str:
    """Id no formato de uuid4 hex, porém derivado de ``_RNG``.

    ``uuid.uuid4()`` lê de ``os.urandom`` e ignora a semente fixada por
    ``fixar_semente``, o que quebraria a reprodutibilidade prometida por
    ``fixar_semente``/``--seed``.
    """
    return uuid.UUID(int=_RNG.getrandbits(128), version=4).hex


def _prefixo_cep() -> str:
    return str(fake.random_int(10000, 99999))


def gerar_customers(n: int) -> list[tuple]:
    """Clientes: customer_id único + customer_unique_id (a pessoa por trás)."""
    return [
        (
            _novo_id(),
            _novo_id(),
            _prefixo_cep(),
            fake.city(),
            _RNG.choice(CUSTOMER_STATES),
        )
        for _ in range(n)
    ]


def gerar_sellers(n: int) -> list[tuple]:
    return [
        (_novo_id(), _prefixo_cep(), fake.city(), _RNG.choice(CUSTOMER_STATES))
        for _ in range(n)
    ]


def gerar_geolocation(n: int) -> list[tuple]:
    return [
        (
            _prefixo_cep(),
            float(fake.latitude()),
            float(fake.longitude()),
            fake.city(),
            _RNG.choice(CUSTOMER_STATES),
        )
        for _ in range(n)
    ]


def gerar_products(n: int) -> list[tuple]:
    return [
        (
            _novo_id(),
            _RNG.choice(list(PRODUCT_CATEGORIES)),
            _RNG.randint(20, 60),
            _RNG.randint(100, 3000),
            _RNG.randint(1, 6),
            _RNG.randint(100, 30000),
            _RNG.randint(5, 100),
            _RNG.randint(5, 100),
            _RNG.randint(5, 100),
        )
        for _ in range(n)
    ]


def gerar_grafo_de_pedidos(
    quantidade_de_pedidos: int,
    customer_ids: list[str],
    product_ids: list[str],
    seller_ids: list[str],
) -> dict[str, list[tuple]]:
    """Pedidos + itens + pagamentos + reviews coerentes entre si (FKs válidas)."""
    orders, items, payments, reviews = [], [], [], []
    for _ in range(quantidade_de_pedidos):
        order_id = _novo_id()
        purchased = fake.date_time_between(start_date='-2y', end_date='now')
        approved = purchased + timedelta(hours=_RNG.randint(1, 48))
        delivered = approved + timedelta(days=_RNG.randint(1, 20))
        estimated = purchased + timedelta(days=_RNG.randint(5, 30))
        orders.append(
            (
                order_id,
                _RNG.choice(customer_ids),
                _RNG.choice(ORDER_STATUSES),
                purchased,
                approved,
                approved + timedelta(days=_RNG.randint(1, 5)),
                delivered,
                estimated,
            )
        )
        for item_id in range(1, _RNG.randint(1, 4) + 1):
            items.append(
                (
                    order_id,
                    item_id,
                    _RNG.choice(product_ids),
                    _RNG.choice(seller_ids),
                    approved,
                    round(_RNG.uniform(15.0, 800.0), 2),
                    round(_RNG.uniform(5.0, 60.0), 2),
                )
            )
        payments.append(
            (
                order_id,
                1,
                _RNG.choice(PAYMENT_TYPES),
                _RNG.randint(1, 10),
                round(_RNG.uniform(20.0, 900.0), 2),
            )
        )
        reviews.append(
            (
                _novo_id(),
                order_id,
                _RNG.randint(1, 5),
                None,
                fake.sentence(nb_words=8),
                delivered,
                delivered + timedelta(days=_RNG.randint(1, 3)),
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


def montar_dataset(sizes: dict[str, int]) -> dict[str, list[tuple]]:
    """Gera todas as tabelas já na ordem de carga (dimensões antes dos fatos)."""
    customers = gerar_customers(sizes['customers'])
    sellers = gerar_sellers(sizes['sellers'])
    products = gerar_products(sizes['products'])
    grafo = gerar_grafo_de_pedidos(
        sizes['orders'],
        [row[0] for row in customers],
        [row[0] for row in products],
        [row[0] for row in sellers],
    )
    return {
        'product_category_name_translation': list(PRODUCT_CATEGORIES.items()),
        'customers': customers,
        'sellers': sellers,
        'geolocation': gerar_geolocation(sizes['geolocation']),
        'products': products,
        **grafo,
    }


def copiar_linhas(cursor, table: str, rows: list[tuple]) -> None:
    """Carga em massa via COPY (ordens de magnitude mais rápida que INSERT)."""
    columns = ', '.join(COLUMNS[table])
    with cursor.copy(f'COPY olist.{table} ({columns}) FROM STDIN') as copy:
        for row in rows:
            copy.write_row(row)


def ja_semeado(cursor) -> bool:
    """Idempotência: se já há pedidos, não recarrega nada."""
    cursor.execute('SELECT count(*) FROM olist.orders')
    return cursor.fetchone()[0] > 0


def carregar(cursor, sizes: dict[str, int]) -> dict[str, int]:
    """Carrega o dataset inteiro; retorna a contagem por tabela."""
    dataset = montar_dataset(sizes)
    for table in COLUMNS:
        copiar_linhas(cursor, table, dataset[table])
    return {table: len(rows) for table, rows in dataset.items()}
