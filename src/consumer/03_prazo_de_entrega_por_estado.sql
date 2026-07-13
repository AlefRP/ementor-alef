-- Prazo de entrega e atraso por estado (camada fria).
--
-- Só pedidos efetivamente entregues entram: pedido em trânsito ainda não tem
-- prazo realizado, e incluí-lo puxaria a média para baixo (viés de sobrevivência
-- ao contrário). dias_de_atraso negativo = entregou ANTES do prometido.
SELECT
    cliente.customer_state AS estado,
    COUNT(*) AS pedidos_entregues,
    AVG(pedido.dias_ate_entrega) AS dias_medios_ate_entrega,
    AVG(pedido.dias_de_atraso) AS dias_medios_de_atraso,
    SUM(CASE WHEN pedido.dias_de_atraso > 0 THEN 1 ELSE 0 END) AS entregas_atrasadas,
    CAST(SUM(CASE WHEN pedido.dias_de_atraso > 0 THEN 1 ELSE 0 END) AS DOUBLE)
    / COUNT(*) AS taxa_de_atraso
FROM ${gold_database}.fact_order AS pedido
INNER JOIN ${gold_database}.dim_customer AS cliente
    ON cliente.customer_account_hk = pedido.customer_account_hk
WHERE
    pedido.order_status = 'delivered'
    AND pedido.order_delivered_customer_date IS NOT NULL
GROUP BY cliente.customer_state
ORDER BY taxa_de_atraso DESC;
