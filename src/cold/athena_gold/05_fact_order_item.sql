-- Fato item de pedido (camada fria). Grão: item (order_id + order_item_id).
--
-- É o fato de RECEITA: preço e frete vivem aqui, não no cabeçalho do pedido.
-- Somar receita a partir de fact_order daria errado (um pedido tem N itens).
CREATE OR REPLACE VIEW ${gold_database}.fact_order_item AS
WITH preco_atual AS (
    SELECT
        link_order_item_hk,
        shipping_limit_date,
        price,
        freight_value
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.link_order_item_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_order_item_pricing AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    item.link_order_item_hk,
    item.order_hk,
    item.product_hk,
    item.seller_hk,
    item.order_item_id,
    preco.shipping_limit_date,
    preco.price,
    preco.freight_value,
    preco.price + preco.freight_value AS valor_total_item
FROM ${silver_database}.link_order_item AS item
LEFT JOIN preco_atual AS preco
    ON preco.link_order_item_hk = item.link_order_item_hk;
