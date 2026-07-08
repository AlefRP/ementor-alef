# api_ec2 — EC2 privada da API de data product (camada fria)

Instância AL2023 em subnet **privada** (sem IP público, sem NAT) que roda a
API FastAPI (`src/cold/api_orders`) via systemd (`api-orders.service`).

Bootstrap 100% offline via S3 gateway endpoint:

1. `dnf` instala o Python 3.11 (repositórios do AL2023 são servidos via S3);
2. o `user_data` baixa o bundle (`api/api-bundle.tar.gz`, gerado pela esteira
   com `make api-bundle`) do bucket de artefatos;
3. `pip install --no-index --find-links wheelhouse` instala sem internet.

Autenticação no RDS por **token IAM** (`DB_AUTH=iam`): a role `ec2-api`
assina o token localmente (`rds-db:connect` restrito ao usuário
`api_reader`) — nenhum segredo em runtime, nenhum endpoint pago.

Pré-requisito de banco: rodar `scripts/database/create_api_reader.sql`
(cria o usuário com grant `rds_iam`, leitura apenas no schema `olist`).
