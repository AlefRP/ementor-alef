"""Contrato de dados versionado (v1) de pedidos."""
from datetime import datetime

from pydantic import BaseModel


class Order(BaseModel):
    """Pedido do dataset Olist (``olist.orders``)."""

    order_id: str
    customer_id: str
    order_status: str
    order_purchase_timestamp: datetime | None = None
    order_approved_at: datetime | None = None
    order_delivered_carrier_date: datetime | None = None
    order_delivered_customer_date: datetime | None = None
    order_estimated_delivery_date: datetime | None = None


class PageCursor(BaseModel):
    """Cursor keyset da próxima página (ordenação estável compra + id)."""

    purchased_after: datetime
    after_id: str


class OrdersPage(BaseModel):
    """Página de pedidos; ``next_cursor`` é ``null`` na última página."""

    items: list[Order]
    next_cursor: PageCursor | None = None
