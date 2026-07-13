-- Agregado horário dos eventos (camada quente).
--
-- É a view que responde "o streaming está vivo e saudável?": volume, receita e
-- clientes distintos por hora e tipo de evento. Serve de base para o painel da
-- camada quente e para comparar o ritmo do quente com o batch do frio.
CREATE OR REPLACE VIEW ${gold_database}.agg_order_event_hourly AS
SELECT
    DATE_TRUNC('hour', event_timestamp) AS hora,
    event_type,
    product_category_name,
    COUNT(*) AS eventos,
    COUNT(DISTINCT order_hk) AS pedidos_distintos,
    COUNT(DISTINCT customer_hk) AS clientes_distintos,
    SUM(valor_total_evento) AS valor_total,
    AVG(valor_total_evento) AS ticket_medio
FROM ${gold_database}.fact_order_event
WHERE event_timestamp IS NOT NULL
GROUP BY
    DATE_TRUNC('hour', event_timestamp),
    event_type,
    product_category_name;
