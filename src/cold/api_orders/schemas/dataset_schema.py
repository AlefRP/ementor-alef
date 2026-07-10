"""Contratos de dados versionados (v1) dos demais datasets do Olist.

Cada modelo espelha as colunas da tabela homônima em ``olist.*``; a ordem dos
campos define a ordem do SELECT gerado em ``endpoints/_tables.py``.
"""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

ItemT = TypeVar('ItemT', bound=BaseModel)


class DatasetPage(BaseModel, Generic[ItemT]):
    """Página de um dataset; ``next_cursor`` vem sempre que há itens.

    Ao contrário de ``/v1/orders`` (incremental por timestamp), o cursor aqui
    é opaco: a lista de valores da chave do último item, ecoada pelo cliente
    no parâmetro ``after`` (um valor por coluna da chave, na mesma ordem).
    """

    items: list[ItemT]
    next_cursor: list[str] | None = None


class Customer(BaseModel):
    """Cliente (``olist.customers``)."""

    customer_id: str
    customer_unique_id: str
    customer_zip_code_prefix: str | None = None
    customer_city: str | None = None
    customer_state: str | None = None


class Seller(BaseModel):
    """Vendedor (``olist.sellers``)."""

    seller_id: str
    seller_zip_code_prefix: str | None = None
    seller_city: str | None = None
    seller_state: str | None = None


class Product(BaseModel):
    """Produto (``olist.products``) — nomes com typo preservados do CSV."""

    product_id: str
    product_category_name: str | None = None
    product_name_lenght: int | None = None
    product_description_lenght: int | None = None
    product_photos_qty: int | None = None
    product_weight_g: int | None = None
    product_length_cm: int | None = None
    product_height_cm: int | None = None
    product_width_cm: int | None = None


class Geolocation(BaseModel):
    """Coordenada por prefixo de CEP (``olist.geolocation``)."""

    geolocation_id: int
    geolocation_zip_code_prefix: str | None = None
    geolocation_lat: float | None = None
    geolocation_lng: float | None = None
    geolocation_city: str | None = None
    geolocation_state: str | None = None


class CategoryTranslation(BaseModel):
    """Tradução de categoria (``olist.product_category_name_translation``)."""

    product_category_name: str
    product_category_name_english: str | None = None


class OrderItem(BaseModel):
    """Item de pedido (``olist.order_items``)."""

    order_id: str
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_date: datetime | None = None
    price: float | None = None
    freight_value: float | None = None


class OrderPayment(BaseModel):
    """Pagamento de pedido (``olist.order_payments``)."""

    order_id: str
    payment_sequential: int
    payment_type: str | None = None
    payment_installments: int | None = None
    payment_value: float | None = None


class OrderReview(BaseModel):
    """Avaliação de pedido (``olist.order_reviews``)."""

    review_id: str
    order_id: str
    review_score: int | None = None
    review_comment_title: str | None = None
    review_comment_message: str | None = None
    review_creation_date: datetime | None = None
    review_answer_timestamp: datetime | None = None

