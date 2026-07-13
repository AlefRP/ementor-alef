-- Fato pedido (camada fria). Grão: um pedido (order_id).
--
-- Cabeçalho do pedido com o ciclo de vida (compra -> aprovação -> transporte ->
-- entrega) e os prazos derivados que a operação cobra: dias até entregar e
-- atraso contra a estimativa (negativo = entregou antes do prometido).
CREATE OR REPLACE VIEW ${gold_database}.fact_order AS
WITH status_atual AS (
    SELECT
        order_hk,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.order_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_order_status AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    pedido.order_hk,
    pedido.order_id,
    vinculo.customer_account_hk,
    estado.order_status,
    estado.order_purchase_timestamp,
    estado.order_approved_at,
    estado.order_delivered_carrier_date,
    estado.order_delivered_customer_date,
    estado.order_estimated_delivery_date,
    DATE(estado.order_purchase_timestamp) AS order_purchase_date,
    DATE_DIFF(
        'day',
        estado.order_purchase_timestamp,
        estado.order_delivered_customer_date
    ) AS dias_ate_entrega,
    DATE_DIFF(
        'day',
        estado.order_estimated_delivery_date,
        estado.order_delivered_customer_date
    ) AS dias_de_atraso
FROM ${silver_database}.hub_order AS pedido
LEFT JOIN ${silver_database}.link_order_customer AS vinculo
    ON vinculo.order_hk = pedido.order_hk
LEFT JOIN status_atual AS estado
    ON estado.order_hk = pedido.order_hk;
