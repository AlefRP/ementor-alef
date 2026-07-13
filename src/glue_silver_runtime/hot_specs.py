"""Schema dos eventos da camada quente e seu mapeamento Data Vault."""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from vault import DatasetVaultSpec, HubSpec, LinkSpec, SatelliteSpec

RECORD_SOURCE_PREFIX = 'raw.hot'

EVENT_SCHEMA = StructType(
    [
        StructField('event_id', StringType(), False),
        StructField('event_type', StringType(), False),
        StructField('event_timestamp', TimestampType(), False),
        StructField(
            'customer',
            StructType(
                [
                    StructField('customer_unique_id', StringType(), False),
                    StructField('customer_name', StringType()),
                    StructField('customer_city', StringType()),
                    StructField('customer_state', StringType()),
                    StructField('customer_zip_code_prefix', StringType()),
                ]
            ),
        ),
        StructField(
            'order',
            StructType(
                [
                    StructField('order_id', StringType(), False),
                    StructField('product_category_name', StringType()),
                    StructField('product_name', StringType()),
                    StructField('items_count', IntegerType()),
                    StructField('price', DoubleType()),
                    StructField('freight_value', DoubleType()),
                ]
            ),
        ),
        StructField(
            'payment',
            StructType(
                [
                    StructField('payment_type', StringType()),
                    StructField('payment_installments', IntegerType()),
                ]
            ),
        ),
    ]
)

# hub_order e hub_customer são os MESMOS hubs carregados pela camada fria:
# integração por chave de negócio é o princípio central do DV 2.0.
EVENT_VAULT = DatasetVaultSpec(
    hubs=[
        HubSpec('hub_event', 'event_hk', 'event_id', ['event_id']),
        HubSpec('hub_order', 'order_hk', 'order_id', ['order_id']),
        HubSpec(
            'hub_customer',
            'customer_hk',
            'customer_unique_id',
            ['customer_unique_id'],
        ),
    ],
    links=[
        LinkSpec(
            'link_event_order',
            'link_event_order_hk',
            ['event_id', 'order_id'],
            {'event_hk': ['event_id'], 'order_hk': ['order_id']},
        ),
        LinkSpec(
            'link_event_customer',
            'link_event_customer_hk',
            ['event_id', 'customer_unique_id'],
            {
                'event_hk': ['event_id'],
                'customer_hk': ['customer_unique_id'],
            },
        ),
    ],
    satellites=[
        SatelliteSpec(
            'sat_event_context',
            'event_hk',
            ['event_id'],
            ['event_type', 'event_timestamp', 'raw_file', 'raw_partition_date'],
        ),
        SatelliteSpec(
            'sat_hot_customer_profile',
            'customer_hk',
            ['customer_unique_id'],
            [
                'customer_name',
                'customer_city',
                'customer_state',
                'customer_zip_code_prefix',
            ],
        ),
        SatelliteSpec(
            'sat_hot_order_snapshot',
            'order_hk',
            ['order_id'],
            [
                'product_category_name',
                'product_name',
                'items_count',
                'price',
                'freight_value',
            ],
        ),
        # O pagamento é do pedido naquele evento — contexto do relacionamento,
        # não do evento em si; por isso pendura no link_event_order.
        SatelliteSpec(
            'sat_hot_payment_snapshot',
            'link_event_order_hk',
            ['event_id', 'order_id'],
            ['payment_type', 'payment_installments'],
        ),
    ],
)


def achatar_eventos(df: DataFrame) -> DataFrame:
    """Achata o evento aninhado (customer/order/payment) em colunas planas."""
    return df.select(
        'event_id',
        'event_type',
        'event_timestamp',
        F.col('customer.customer_unique_id').alias('customer_unique_id'),
        F.col('customer.customer_name').alias('customer_name'),
        F.col('customer.customer_city').alias('customer_city'),
        F.col('customer.customer_state').alias('customer_state'),
        F.col('customer.customer_zip_code_prefix').alias('customer_zip_code_prefix'),
        F.col('order.order_id').alias('order_id'),
        F.col('order.product_category_name').alias('product_category_name'),
        F.col('order.product_name').alias('product_name'),
        F.col('order.items_count').alias('items_count'),
        F.col('order.price').alias('price'),
        F.col('order.freight_value').alias('freight_value'),
        F.col('payment.payment_type').alias('payment_type'),
        F.col('payment.payment_installments').alias('payment_installments'),
        'raw_file',
        'raw_partition_date',
        'load_dts',
        'record_source',
    )
