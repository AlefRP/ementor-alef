-- Fato avaliação (camada fria). Grão: avaliação (review_id).
--
-- O satélite da review pendura no hub_review; o pedido avaliado chega pelo
-- link_order_review. review_score de 1 a 5 é a métrica de satisfação (NPS-like).
CREATE OR REPLACE VIEW ${gold_database}.fact_order_review AS
WITH review_atual AS (
    SELECT
        review_hk,
        review_score,
        review_comment_title,
        review_creation_date,
        review_answer_timestamp
    FROM (
        SELECT
            sat.*,
            ROW_NUMBER() OVER (
                PARTITION BY sat.review_hk ORDER BY sat.load_dts DESC
            ) AS versao
        FROM ${silver_database}.sat_order_review AS sat
    ) AS versionado
    WHERE versao = 1
)
SELECT
    avaliacao.review_hk,
    avaliacao.review_id,
    vinculo.order_hk,
    detalhe.review_score,
    detalhe.review_comment_title,
    detalhe.review_creation_date,
    detalhe.review_answer_timestamp,
    DATE_DIFF(
        'day',
        detalhe.review_creation_date,
        detalhe.review_answer_timestamp
    ) AS dias_ate_resposta
FROM ${silver_database}.hub_review AS avaliacao
LEFT JOIN ${silver_database}.link_order_review AS vinculo
    ON vinculo.review_hk = avaliacao.review_hk
LEFT JOIN review_atual AS detalhe
    ON detalhe.review_hk = avaliacao.review_hk;
