-- Fato evento de pedido (camada quente). Grão: um evento (event_id).
--
-- Cada transição de estado do pedido (created, approved, invoiced, shipped,
-- delivered) é uma linha. O hub_order e o hub_customer são os MESMOS da camada
-- fria — é assim que o evento quente se liga ao pedido histórico frio.
--
-- Nota de modelagem: sat_hot_order_snapshot tem grão de PEDIDO, não de evento;
-- a versão corrente dele é o último snapshot conhecido do pedido, não o estado
-- no instante daquele evento. Para "estado no momento do evento", use
-- event_type/event_timestamp, que são do próprio evento.
CREATE OR REPLACE VIEW ${gold_database}.fact_order_event AS
WITH contexto_atual AS (
    SELECT
        event_hk,
        event_type,
        event_timestamp,
        raw_partition_date
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.event_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_event_context AS sat
    ) AS versionado
    WHERE versao = 1
),

pedido_atual AS (
    SELECT
        order_hk,
        product_category_name,
        items_count,
        price,
        freight_value
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.order_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_hot_order_snapshot AS sat
    ) AS versionado
    WHERE versao = 1
),

pagamento_atual AS (
    SELECT
        link_event_order_hk,
        payment_type,
        payment_installments
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.link_event_order_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_hot_payment_snapshot AS sat
    ) AS versionado
    WHERE versao = 1
)

SELECT
    evento.event_hk,
    evento.event_id,
    contexto.event_type,
    contexto.event_timestamp,
    contexto.raw_partition_date,
    vinculo_pedido.order_hk,
    vinculo_cliente.customer_hk,
    pedido.product_category_name,
    pedido.items_count,
    pedido.price,
    pedido.freight_value,
    pedido.price + pedido.freight_value AS valor_total_evento,
    pagamento.payment_type,
    pagamento.payment_installments
FROM ${silver_database}.hub_event AS evento
LEFT JOIN contexto_atual AS contexto
    ON contexto.event_hk = evento.event_hk
LEFT JOIN ${silver_database}.link_event_order AS vinculo_pedido
    ON vinculo_pedido.event_hk = evento.event_hk
LEFT JOIN ${silver_database}.link_event_customer AS vinculo_cliente
    ON vinculo_cliente.event_hk = evento.event_hk
LEFT JOIN pedido_atual AS pedido
    ON pedido.order_hk = vinculo_pedido.order_hk
LEFT JOIN pagamento_atual AS pagamento
    ON pagamento.link_event_order_hk = vinculo_pedido.link_event_order_hk;
