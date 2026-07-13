"""Contrato de dados versionado (v1) dos eventos de pedido.

O formato espelha o que a silver da camada quente espera (ver
``glue_silver_runtime/hot_specs.py``): validar aqui, na borda, é o que impede
evento malformado de chegar à raw e quebrar o microbatch lá na frente.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from src.hot.api_events.core.configs import MAX_EVENTS_POR_REQUISICAO


class Cliente(BaseModel):
    """Cliente que originou o evento."""

    customer_unique_id: str
    customer_name: str
    customer_city: str
    customer_state: str = Field(min_length=2, max_length=2)
    customer_zip_code_prefix: str


class Pedido(BaseModel):
    """Pedido e o item que o evento carrega."""

    order_id: str
    product_category_name: str
    product_name: str
    items_count: int = Field(ge=1)
    price: float = Field(ge=0)
    freight_value: float = Field(ge=0)


class Pagamento(BaseModel):
    """Forma de pagamento do pedido."""

    payment_type: str
    payment_installments: int = Field(ge=1)


class EventoPedido(BaseModel):
    """Transição de estado de um pedido (``order_created``, ``order_paid``...)."""

    event_id: str
    event_type: str
    event_timestamp: datetime
    customer: Cliente
    order: Pedido
    payment: Pagamento


class LoteDeEventos(BaseModel):
    """Lote publicado numa requisição (o produtor pagina acima do teto)."""

    events: list[EventoPedido] = Field(
        min_length=1, max_length=MAX_EVENTS_POR_REQUISICAO
    )


class RespostaPublicacao(BaseModel):
    """Recibo da publicação; ``correlation_id`` liga o request aos logs."""

    published: int
    correlation_id: str
