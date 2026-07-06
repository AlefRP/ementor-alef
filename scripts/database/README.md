# Seed do banco de origem (Olist)

Carga **única e idempotente** do [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(~100k pedidos reais anonimizados de e-commerce brasileiro, 2016–2018; licença
CC BY-NC-SA 4.0) no RDS PostgreSQL provisionado pelo Terraform.

Os CSVs são baixados do espelho público
[mara/mara-olist-ecommerce-data](https://github.com/mara/mara-olist-ecommerce-data)
(sem necessidade de conta no Kaggle).

## Arquivos

- `olist_schema.sql` — DDL das 9 tabelas no schema `olist` (PKs, FKs, índices).
- `seed_olist.sh` — baixa os CSVs e carrega via `psql \copy`. **Se
  `olist.orders` já tiver dados, sai sem fazer nada** (a carga é única).

## Como rodar

O RDS é privado; rode de um host com acesso (EC2 da API via `user_data` na
story da API, ou bastion/túnel SSM):

```bash
PGHOST=$(terraform -chdir=infra/terraform/environments/prod output -raw database_endpoint | cut -d: -f1) \
SECRET_ARN=$(terraform -chdir=infra/terraform/environments/prod output -raw database_master_secret_arn) \
./scripts/database/seed_olist.sh
```

Requisitos no host: `bash`, `curl`, `psql`, `awscli` (ou exporte `PGPASSWORD`).

## Tabelas (schema `olist`)

`customers`, `sellers`, `products`, `orders`, `order_items`, `order_payments`,
`order_reviews`, `geolocation`, `product_category_name_translation` — pedidos,
clientes por cidade/UF, pagamentos, fretes e reviews em português.
