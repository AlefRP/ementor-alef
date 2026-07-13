-- Fato pagamento (camada fria). Grão: parcela de pagamento do pedido
-- (order_id + payment_sequential) — um pedido pode ser pago com mais de um
-- meio (ex.: voucher + cartão), e cada um é uma linha.
CREATE OR REPLACE VIEW ${gold_database}.fact_order_payment AS
WITH pagamento_atual AS (
    SELECT
        link_order_payment_hk,
        payment_type,
        payment_installments,
        payment_value
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.link_order_payment_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_order_payment AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    pagamento.link_order_payment_hk,
    pagamento.order_hk,
    pagamento.payment_sequential,
    detalhe.payment_type,
    detalhe.payment_installments,
    detalhe.payment_value
FROM ${silver_database}.link_order_payment AS pagamento
LEFT JOIN pagamento_atual AS detalhe
    ON detalhe.link_order_payment_hk = pagamento.link_order_payment_hk;
