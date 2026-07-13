-- Dimensão vendedor (camada fria). Grão: seller_id.
CREATE OR REPLACE VIEW ${gold_database}.dim_seller AS
WITH perfil_atual AS (
    SELECT
        seller_hk,
        seller_zip_code_prefix,
        seller_city,
        seller_state
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.seller_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_seller_profile AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    vendedor.seller_hk,
    vendedor.seller_id,
    perfil.seller_zip_code_prefix,
    perfil.seller_city,
    perfil.seller_state,
    geo.geolocation_lat AS seller_lat,
    geo.geolocation_lng AS seller_lng
FROM ${silver_database}.hub_seller AS vendedor
LEFT JOIN perfil_atual AS perfil
    ON perfil.seller_hk = vendedor.seller_hk
LEFT JOIN ${silver_database}.ref_geolocation AS geo
    ON geo.geolocation_zip_code_prefix = perfil.seller_zip_code_prefix;
