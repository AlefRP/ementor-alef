# Seed do banco de origem (Olist)

Carga **única e idempotente** do [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(~100k pedidos reais anonimizados de e-commerce brasileiro, 2016–2018; licença
CC BY-NC-SA 4.0) no RDS PostgreSQL provisionado pelo Terraform.

Os CSVs são baixados do espelho público
[mara/mara-olist-ecommerce-data](https://github.com/mara/mara-olist-ecommerce-data)
(sem necessidade de conta no Kaggle).

## Arquivos

- `olist_schema.sql` — DDL das 9 tabelas no schema `olist` (PKs, FKs, índices).
- `seed_olist.sh` — baixa os CSVs **reais** do Olist e carrega via `psql \copy`.
  **Se `olist.orders` já tiver dados, sai sem fazer nada** (a carga é única).
- `seed_synthetic.py` — alternativa **sintética (Faker)**: gera as 9 tabelas com
  integridade referencial e volume controlável, sem depender de fonte externa.
  Vocabulário (categorias/UFs/pagamentos) consistente com os eventos da camada
  quente (`src/hot/event_producer/handler.py`) — ideal para um ETL que junta as
  camadas fria e quente. Também idempotente.

## Dados reais vs. sintéticos

- **Reais** (`seed_olist.sh`): ~100k pedidos de 2016–2018; snapshot estático.
- **Sintéticos** (`seed_synthetic.py`): volume à sua escolha, dados "frescos",
  reprodutíveis com `--seed`. Use quando quiser controlar tamanho ou simular
  ETLs incrementais sem a fonte externa.

```bash
PGHOST=$(terraform -chdir=infra/terraform/environments/prod output -raw database_endpoint | cut -d: -f1) \
SECRET_ARN=$(terraform -chdir=infra/terraform/environments/prod output -raw database_master_secret_arn) \
python scripts/database/seed_synthetic.py --orders 5000 --customers 2000

# Requisitos no host: pip install 'psycopg[binary]' faker
```

## Como rodar

O RDS é privado; rode de um host com acesso (EC2 da API via `user_data` na
story da API, ou bastion/túnel SSM):

```bash
PGHOST=$(terraform -chdir=infra/terraform/environments/prod output -raw database_endpoint | cut -d: -f1) \
SECRET_ARN=$(terraform -chdir=infra/terraform/environments/prod output -raw database_master_secret_arn) \
./scripts/database/seed_olist.sh
```

Requisitos no host: `bash`, `curl`, `psql`, `awscli` (ou exporte `PGPASSWORD`).

## Usuário da API (IAM auth)

Depois do seed, crie o usuário de leitura da API (token IAM, sem senha):

```bash
psql -v ON_ERROR_STOP=1 -f scripts/database/create_api_reader.sql
```

## Tabelas (schema `olist`)

`customers`, `sellers`, `products`, `orders`, `order_items`, `order_payments`,
`order_reviews`, `geolocation`, `product_category_name_translation` — pedidos,
clientes por cidade/UF, pagamentos, fretes e reviews em português.
