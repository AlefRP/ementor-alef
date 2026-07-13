-- Dimensão produto (camada fria).
--
-- Grão: product_id. A categoria vem traduzida pela reference table do DV
-- (ref_product_category) — é para isso que a tabela de tradução existe.
CREATE OR REPLACE VIEW ${gold_database}.dim_product AS
WITH detalhe_atual AS (
    SELECT
        product_hk,
        product_category_name,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm,
        product_photos_qty
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.product_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_product_details AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    produto.product_hk,
    produto.product_id,
    detalhe.product_category_name,
    COALESCE(
        categoria.product_category_name_english,
        detalhe.product_category_name
    ) AS product_category_name_english,
    detalhe.product_weight_g,
    detalhe.product_photos_qty,
    -- Volume em cm3: usado no custo de frete e na análise de logística.
    detalhe.product_length_cm
        * detalhe.product_height_cm
        * detalhe.product_width_cm AS product_volume_cm3
FROM ${silver_database}.hub_product AS produto
LEFT JOIN detalhe_atual AS detalhe
    ON detalhe.product_hk = produto.product_hk
LEFT JOIN ${silver_database}.ref_product_category AS categoria
    ON categoria.product_category_name = detalhe.product_category_name;
