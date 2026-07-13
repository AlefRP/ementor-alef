-- Funil de eventos do pedido (camada quente).
--
-- Conta pedidos distintos que alcançaram cada estágio e a conversão contra o
-- estágio inicial (order_created). Queda abrupta entre dois estágios é o sinal
-- que o painel da camada quente existe para mostrar.
WITH por_estagio AS (
    SELECT
        event_type AS estagio,
        COUNT(DISTINCT order_hk) AS pedidos
    FROM ${gold_database}.fact_order_event
    WHERE order_hk IS NOT NULL
    GROUP BY event_type
),

base AS (
    SELECT MAX(pedidos) AS pedidos_no_topo FROM por_estagio
)

SELECT
    estagio.estagio,
    estagio.pedidos,
    CAST(estagio.pedidos AS DOUBLE) / base.pedidos_no_topo AS conversao_do_topo
FROM por_estagio AS estagio
CROSS JOIN base
ORDER BY estagio.pedidos DESC;
