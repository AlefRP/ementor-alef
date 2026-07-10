-- Schema do dataset Olist (e-commerce brasileiro, ~100k pedidos 2016-2018).
-- Fonte: Brazilian E-Commerce Public Dataset by Olist (CC BY-NC-SA 4.0).
-- Obs.: os nomes "lenght" vêm assim (typo) nos CSVs originais — mantidos para
-- casar com o \copy direto dos arquivos.

BEGIN;

CREATE SCHEMA IF NOT EXISTS olist;

CREATE TABLE IF NOT EXISTS olist.product_category_name_translation (
    product_category_name         text PRIMARY KEY,
    product_category_name_english text
);

CREATE TABLE IF NOT EXISTS olist.customers (
    customer_id              text PRIMARY KEY,
    customer_unique_id       text NOT NULL,
    customer_zip_code_prefix text,
    customer_city            text,
    customer_state           char(2)
);

CREATE TABLE IF NOT EXISTS olist.sellers (
    seller_id              text PRIMARY KEY,
    seller_zip_code_prefix text,
    seller_city            text,
    seller_state           char(2)
);

-- Sem PK natural: o CSV original tem linhas duplicadas por natureza (várias
-- coordenadas por prefixo de CEP). geolocation_id (identity) dá a ordenação
-- estável que o keyset da API exige; o ALTER cobre bancos semeados antes de a
-- coluna existir (idempotente, backfill automático).
CREATE TABLE IF NOT EXISTS olist.geolocation (
    geolocation_id              bigint GENERATED ALWAYS AS IDENTITY,
    geolocation_zip_code_prefix text,
    geolocation_lat             double precision,
    geolocation_lng             double precision,
    geolocation_city            text,
    geolocation_state           char(2)
);

ALTER TABLE olist.geolocation
    ADD COLUMN IF NOT EXISTS geolocation_id bigint GENERATED ALWAYS AS IDENTITY;

CREATE TABLE IF NOT EXISTS olist.products (
    product_id                 text PRIMARY KEY,
    product_category_name      text,
    product_name_lenght        integer,
    product_description_lenght integer,
    product_photos_qty         integer,
    product_weight_g           integer,
    product_length_cm          integer,
    product_height_cm          integer,
    product_width_cm           integer
);

CREATE TABLE IF NOT EXISTS olist.orders (
    order_id                      text PRIMARY KEY,
    customer_id                   text NOT NULL REFERENCES olist.customers (customer_id),
    order_status                  text NOT NULL,
    order_purchase_timestamp      timestamp,
    order_approved_at             timestamp,
    order_delivered_carrier_date  timestamp,
    order_delivered_customer_date timestamp,
    order_estimated_delivery_date timestamp
);

CREATE TABLE IF NOT EXISTS olist.order_items (
    order_id            text NOT NULL REFERENCES olist.orders (order_id),
    order_item_id       integer NOT NULL,
    product_id          text NOT NULL REFERENCES olist.products (product_id),
    seller_id           text NOT NULL REFERENCES olist.sellers (seller_id),
    shipping_limit_date timestamp,
    price               numeric(10, 2),
    freight_value       numeric(10, 2),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS olist.order_payments (
    order_id             text NOT NULL REFERENCES olist.orders (order_id),
    payment_sequential   integer NOT NULL,
    payment_type         text,
    payment_installments integer,
    payment_value        numeric(10, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

-- review_id NÃO é único no dataset original (mesma avaliação referenciando
-- pedidos distintos); a PK composta reflete isso.
CREATE TABLE IF NOT EXISTS olist.order_reviews (
    review_id               text NOT NULL,
    order_id                text NOT NULL REFERENCES olist.orders (order_id),
    review_score            integer,
    review_comment_title    text,
    review_comment_message  text,
    review_creation_date    timestamp,
    review_answer_timestamp timestamp,
    PRIMARY KEY (review_id, order_id)
);

-- Índices para os padrões de acesso da API de data product.
CREATE INDEX IF NOT EXISTS idx_orders_purchase_ts ON olist.orders (order_purchase_timestamp);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON olist.orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON olist.order_items (product_id);
CREATE INDEX IF NOT EXISTS idx_customers_state ON olist.customers (customer_state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_geolocation_id ON olist.geolocation (geolocation_id);

COMMIT;
