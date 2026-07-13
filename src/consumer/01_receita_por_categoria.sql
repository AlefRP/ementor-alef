-- Receita e frete por categoria de produto (camada fria).
--
-- A receita vem do fato ITEM (grão de item), nunca do cabeçalho do pedido —
-- somar por pedido contaria o mesmo pedido N vezes quando ele tem N itens.
SELECT
    produto.product_category_name_english AS categoria,
    COUNT(DISTINCT item.order_hk) AS pedidos,
    COUNT(*) AS itens,
    SUM(item.price) AS receita,
    SUM(item.freight_value) AS frete,
    AVG(item.price) AS preco_medio_item
FROM ${gold_database}.fact_order_item AS item
INNER JOIN ${gold_database}.dim_product AS produto
    ON produto.product_hk = item.product_hk
GROUP BY produto.product_category_name_english
ORDER BY receita DESC
LIMIT 20;
