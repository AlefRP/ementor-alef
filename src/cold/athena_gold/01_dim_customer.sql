-- Dimensão cliente (camada fria).
--
-- Grão: CONTA do cliente (customer_id). No Olist, customer_id é único por
-- pedido; a identidade real é customer_unique_id — por isso a dimensão carrega
-- as duas chaves: junte fatos por customer_account_hk e conte gente distinta
-- por customer_unique_id.
CREATE OR REPLACE VIEW ${gold_database}.dim_customer AS
WITH perfil_atual AS (
    SELECT
        customer_account_hk,
        customer_zip_code_prefix,
        customer_city,
        customer_state
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.customer_account_hk
                ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_customer_profile AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    conta.customer_account_hk,
    conta.customer_id,
    cliente.customer_hk,
    cliente.customer_unique_id,
    perfil.customer_zip_code_prefix,
    perfil.customer_city,
    perfil.customer_state,
    geo.geolocation_lat AS customer_lat,
    geo.geolocation_lng AS customer_lng
FROM ${silver_database}.hub_customer_account AS conta
INNER JOIN ${silver_database}.link_customer_account AS vinculo
    ON vinculo.customer_account_hk = conta.customer_account_hk
INNER JOIN ${silver_database}.hub_customer AS cliente
    ON cliente.customer_hk = vinculo.customer_hk
LEFT JOIN perfil_atual AS perfil
    ON perfil.customer_account_hk = conta.customer_account_hk
LEFT JOIN ${silver_database}.ref_geolocation AS geo
    ON geo.geolocation_zip_code_prefix = perfil.customer_zip_code_prefix;
