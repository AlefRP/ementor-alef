-- Usuário de leitura da API de data product (camada fria) com IAM auth:
-- sem senha — o login usa token do RDS (grant rds_iam) assinado pela role
-- ec2-api. Escopo mínimo: SELECT no schema olist, nada além.
-- Rode uma vez, conectado como master (mesmo canal usado pelo seed).

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_reader') THEN
        CREATE ROLE api_reader WITH LOGIN;
    END IF;
END
$$;

GRANT rds_iam TO api_reader;
GRANT USAGE ON SCHEMA olist TO api_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA olist TO api_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA olist GRANT SELECT ON TABLES TO api_reader;
