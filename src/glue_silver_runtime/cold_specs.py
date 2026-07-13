"""Schemas dos datasets Olist da camada fria e seu mapeamento Data Vault."""
from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from vault import DatasetVaultSpec, HubSpec, LinkSpec, ReferenceSpec, SatelliteSpec

RECORD_SOURCE_PREFIX = 'raw.olist'


@dataclass(frozen=True)
class ColdDatasetSpec:
    schema: StructType
    vault: DatasetVaultSpec


def estrutura(*campos: StructField) -> StructType:
    """Atalho legível para montar o StructType de um dataset."""
    return StructType(list(campos))


# No Olist, customer_id é único POR PEDIDO (conta); a identidade real do
# cliente é customer_unique_id. O hub_customer usa a chave de negócio e o
# same-as link mapeia conta -> cliente, integrando as camadas fria e quente.
CUSTOMERS = ColdDatasetSpec(
    schema=estrutura(
        StructField('customer_id', StringType(), False),
        StructField('customer_unique_id', StringType(), False),
        StructField('customer_zip_code_prefix', StringType()),
        StructField('customer_city', StringType()),
        StructField('customer_state', StringType()),
    ),
    vault=DatasetVaultSpec(
        hubs=[
            HubSpec(
                'hub_customer',
                'customer_hk',
                'customer_unique_id',
                ['customer_unique_id'],
            ),
            HubSpec(
                'hub_customer_account',
                'customer_account_hk',
                'customer_id',
                ['customer_id'],
            ),
        ],
        links=[
            LinkSpec(
                'link_customer_account',
                'link_customer_account_hk',
                ['customer_id', 'customer_unique_id'],
                {
                    'customer_account_hk': ['customer_id'],
                    'customer_hk': ['customer_unique_id'],
                },
            )
        ],
        satellites=[
            SatelliteSpec(
                'sat_customer_profile',
                'customer_account_hk',
                ['customer_id'],
                [
                    'customer_zip_code_prefix',
                    'customer_city',
                    'customer_state',
                ],
            )
        ],
    ),
)

SELLERS = ColdDatasetSpec(
    schema=estrutura(
        StructField('seller_id', StringType(), False),
        StructField('seller_zip_code_prefix', StringType()),
        StructField('seller_city', StringType()),
        StructField('seller_state', StringType()),
    ),
    vault=DatasetVaultSpec(
        hubs=[HubSpec('hub_seller', 'seller_hk', 'seller_id', ['seller_id'])],
        satellites=[
            SatelliteSpec(
                'sat_seller_profile',
                'seller_hk',
                ['seller_id'],
                ['seller_zip_code_prefix', 'seller_city', 'seller_state'],
            )
        ],
    ),
)

PRODUCTS = ColdDatasetSpec(
    schema=estrutura(
        StructField('product_id', StringType(), False),
        StructField('product_category_name', StringType()),
        StructField('product_name_lenght', IntegerType()),
        StructField('product_description_lenght', IntegerType()),
        StructField('product_photos_qty', IntegerType()),
        StructField('product_weight_g', IntegerType()),
        StructField('product_length_cm', IntegerType()),
        StructField('product_height_cm', IntegerType()),
        StructField('product_width_cm', IntegerType()),
    ),
    vault=DatasetVaultSpec(
        hubs=[HubSpec('hub_product', 'product_hk', 'product_id', ['product_id'])],
        satellites=[
            SatelliteSpec(
                'sat_product_details',
                'product_hk',
                ['product_id'],
                [
                    'product_category_name',
                    'product_name_lenght',
                    'product_description_lenght',
                    'product_photos_qty',
                    'product_weight_g',
                    'product_length_cm',
                    'product_height_cm',
                    'product_width_cm',
                ],
            )
        ],
    ),
)

ORDERS = ColdDatasetSpec(
    schema=estrutura(
        StructField('order_id', StringType(), False),
        StructField('customer_id', StringType(), False),
        StructField('order_status', StringType(), False),
        StructField('order_purchase_timestamp', TimestampType()),
        StructField('order_approved_at', TimestampType()),
        StructField('order_delivered_carrier_date', TimestampType()),
        StructField('order_delivered_customer_date', TimestampType()),
        StructField('order_estimated_delivery_date', TimestampType()),
    ),
    vault=DatasetVaultSpec(
        hubs=[HubSpec('hub_order', 'order_hk', 'order_id', ['order_id'])],
        links=[
            LinkSpec(
                'link_order_customer',
                'link_order_customer_hk',
                ['order_id', 'customer_id'],
                {'order_hk': ['order_id'], 'customer_account_hk': ['customer_id']},
            )
        ],
        satellites=[
            SatelliteSpec(
                'sat_order_status',
                'order_hk',
                ['order_id'],
                [
                    'order_status',
                    'order_purchase_timestamp',
                    'order_approved_at',
                    'order_delivered_carrier_date',
                    'order_delivered_customer_date',
                    'order_estimated_delivery_date',
                ],
            )
        ],
    ),
)

ORDER_ITEMS = ColdDatasetSpec(
    schema=estrutura(
        StructField('order_id', StringType(), False),
        StructField('order_item_id', IntegerType(), False),
        StructField('product_id', StringType(), False),
        StructField('seller_id', StringType(), False),
        StructField('shipping_limit_date', TimestampType()),
        StructField('price', DoubleType()),
        StructField('freight_value', DoubleType()),
    ),
    vault=DatasetVaultSpec(
        links=[
            LinkSpec(
                'link_order_item',
                'link_order_item_hk',
                ['order_id', 'order_item_id', 'product_id', 'seller_id'],
                {
                    'order_hk': ['order_id'],
                    'product_hk': ['product_id'],
                    'seller_hk': ['seller_id'],
                },
                ['order_item_id'],
            )
        ],
        satellites=[
            SatelliteSpec(
                'sat_order_item_pricing',
                'link_order_item_hk',
                ['order_id', 'order_item_id', 'product_id', 'seller_id'],
                ['shipping_limit_date', 'price', 'freight_value'],
            )
        ],
    ),
)

ORDER_PAYMENTS = ColdDatasetSpec(
    schema=estrutura(
        StructField('order_id', StringType(), False),
        StructField('payment_sequential', IntegerType(), False),
        StructField('payment_type', StringType()),
        StructField('payment_installments', IntegerType()),
        StructField('payment_value', DoubleType()),
    ),
    vault=DatasetVaultSpec(
        links=[
            LinkSpec(
                'link_order_payment',
                'link_order_payment_hk',
                ['order_id', 'payment_sequential'],
                {'order_hk': ['order_id']},
                ['payment_sequential'],
            )
        ],
        satellites=[
            SatelliteSpec(
                'sat_order_payment',
                'link_order_payment_hk',
                ['order_id', 'payment_sequential'],
                ['payment_type', 'payment_installments', 'payment_value'],
            )
        ],
    ),
)

ORDER_REVIEWS = ColdDatasetSpec(
    schema=estrutura(
        StructField('review_id', StringType(), False),
        StructField('order_id', StringType(), False),
        StructField('review_score', IntegerType()),
        StructField('review_comment_title', StringType()),
        StructField('review_comment_message', StringType()),
        StructField('review_creation_date', TimestampType()),
        StructField('review_answer_timestamp', TimestampType()),
    ),
    vault=DatasetVaultSpec(
        hubs=[HubSpec('hub_review', 'review_hk', 'review_id', ['review_id'])],
        links=[
            LinkSpec(
                'link_order_review',
                'link_order_review_hk',
                ['review_id', 'order_id'],
                {'review_hk': ['review_id'], 'order_hk': ['order_id']},
            )
        ],
        satellites=[
            SatelliteSpec(
                'sat_order_review',
                'review_hk',
                ['review_id'],
                [
                    'order_id',
                    'review_score',
                    'review_comment_title',
                    'review_comment_message',
                    'review_creation_date',
                    'review_answer_timestamp',
                ],
            )
        ],
    ),
)


def centroide_por_prefixo_de_cep(df: DataFrame) -> DataFrame:
    """Agrega os N pontos de cada prefixo de CEP num centroide determinístico."""
    return df.groupBy('geolocation_zip_code_prefix').agg(
        F.avg('geolocation_lat').alias('geolocation_lat'),
        F.avg('geolocation_lng').alias('geolocation_lng'),
        F.min('geolocation_city').alias('geolocation_city'),
        F.min('geolocation_state').alias('geolocation_state'),
        F.max('load_dts').alias('load_dts'),
        F.min('record_source').alias('record_source'),
    )


# Geolocalização não é objeto de negócio: é lookup descritivo por prefixo de
# CEP (o dado bruto tem N pontos por prefixo — seria um satélite multi-ativo).
GEOLOCATION = ColdDatasetSpec(
    schema=estrutura(
        StructField('geolocation_id', LongType(), False),
        StructField('geolocation_zip_code_prefix', StringType()),
        StructField('geolocation_lat', DoubleType()),
        StructField('geolocation_lng', DoubleType()),
        StructField('geolocation_city', StringType()),
        StructField('geolocation_state', StringType()),
    ),
    vault=DatasetVaultSpec(
        references=[
            ReferenceSpec(
                'ref_geolocation',
                ['geolocation_zip_code_prefix'],
                [
                    'geolocation_lat',
                    'geolocation_lng',
                    'geolocation_city',
                    'geolocation_state',
                ],
                prepare=centroide_por_prefixo_de_cep,
            )
        ],
    ),
)

# Tradução de categoria é reference table (DV 2.0): lookup descritivo, sem
# hash key nem satélite — a categoria segue como atributo nos satellites.
CATEGORY_TRANSLATION = ColdDatasetSpec(
    schema=estrutura(
        StructField('product_category_name', StringType(), False),
        StructField('product_category_name_english', StringType()),
    ),
    vault=DatasetVaultSpec(
        references=[
            ReferenceSpec(
                'ref_product_category',
                ['product_category_name'],
                ['product_category_name_english'],
            )
        ],
    ),
)

DATASETS = {
    'customers': CUSTOMERS,
    'sellers': SELLERS,
    'products': PRODUCTS,
    'orders': ORDERS,
    'order_items': ORDER_ITEMS,
    'order_payments': ORDER_PAYMENTS,
    'order_reviews': ORDER_REVIEWS,
    'geolocation': GEOLOCATION,
    'product_category_name_translation': CATEGORY_TRANSLATION,
}


def datasets_selecionados(entrada: str) -> list[str]:
    """Resolve o argumento --datasets do job: 'all' ou lista com vírgulas."""
    if entrada.strip().lower() == 'all':
        return list(DATASETS)
    return [dataset.strip() for dataset in entrada.split(',') if dataset.strip()]
