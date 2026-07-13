-- Ticket médio por estado do cliente (camada fria).
--
-- Agrega o valor dos itens ATÉ o pedido antes de tirar a média — a média das
-- linhas de item responderia "valor médio do item", não "ticket médio".
WITH valor_por_pedido AS (
    SELECT
        order_hk,
        SUM(valor_total_item) AS valor_pedido
    FROM ${gold_database}.fact_order_item
    GROUP BY order_hk
)

SELECT
    cliente.customer_state AS estado,
    COUNT(*) AS pedidos,
    SUM(valor.valor_pedido) AS receita,
    AVG(valor.valor_pedido) AS ticket_medio,
    APPROX_PERCENTILE(valor.valor_pedido, 0.5) AS ticket_mediano
FROM ${gold_database}.fact_order AS pedido
INNER JOIN valor_por_pedido AS valor
    ON valor.order_hk = pedido.order_hk
INNER JOIN ${gold_database}.dim_customer AS cliente
    ON cliente.customer_account_hk = pedido.customer_account_hk
WHERE cliente.customer_state IS NOT NULL
GROUP BY cliente.customer_state
ORDER BY receita DESC;
