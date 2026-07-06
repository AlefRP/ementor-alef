#!/usr/bin/env bash
# Carga ÚNICA do dataset Olist no RDS PostgreSQL do lakehouse.
#
# Idempotente: se olist.orders já tem linhas, o script encerra sem tocar em nada.
# Pensado para rodar no primeiro boot da EC2 da API (user_data) ou manualmente
# de qualquer host com acesso ao RDS (bastion/túnel).
#
# Requisitos: bash, curl, psql (postgresql-client >= 14), awscli (p/ o secret).
#
# Uso:
#   PGHOST=<endpoint> PGDATABASE=olist PGUSER=lakehouse_admin \
#   SECRET_ARN=<arn do secret do RDS> ./seed_olist.sh
#
#   (alternativa sem awscli: exporte PGPASSWORD diretamente)
set -euo pipefail

: "${PGHOST:?Defina PGHOST com o endpoint do RDS}"
: "${PGDATABASE:=olist}"
: "${PGUSER:=lakehouse_admin}"
export PGHOST PGDATABASE PGUSER

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="https://raw.githubusercontent.com/mara/mara-olist-ecommerce-data/master/data/olist-ecommerce"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# Senha via Secrets Manager (manage_master_user_password), a menos que já venha no ambiente.
if [[ -z "${PGPASSWORD:-}" ]]; then
  : "${SECRET_ARN:?Defina SECRET_ARN (secret do RDS) ou PGPASSWORD}"
  PGPASSWORD="$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_ARN" --query SecretString --output text | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["password"])')"
  export PGPASSWORD
fi

echo ">> Verificando se o banco já foi semeado..."
SEEDED="$(psql -tAc "SELECT COALESCE((SELECT count(*) > 0 FROM olist.orders), false)" 2>/dev/null || echo f)"
if [[ "$SEEDED" == "t" ]]; then
  echo ">> olist.orders já possui dados — nada a fazer (carga é única)."
  exit 0
fi

echo ">> Criando schema..."
psql -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/olist_schema.sql"

# Ordem respeita as FKs: dimensões antes de fatos.
TABLES=(
  "product_category_name_translation:product_category_name_translation.csv"
  "customers:olist_customers_dataset.csv"
  "sellers:olist_sellers_dataset.csv"
  "geolocation:olist_geolocation_dataset.csv"
  "products:olist_products_dataset.csv"
  "orders:olist_orders_dataset.csv"
  "order_items:olist_order_items_dataset.csv"
  "order_payments:olist_order_payments_dataset.csv"
  "order_reviews:olist_order_reviews_dataset.csv"
)

for entry in "${TABLES[@]}"; do
  table="${entry%%:*}"
  file="${entry##*:}"
  echo ">> Baixando ${file}..."
  curl -fsSL --retry 3 -o "$WORKDIR/$file" "$BASE_URL/$file"
  echo ">> Carregando olist.${table}..."
  psql -v ON_ERROR_STOP=1 \
    -c "\\copy olist.${table} FROM '$WORKDIR/$file' WITH (FORMAT csv, HEADER true)"
done

echo ">> Resumo da carga:"
psql -v ON_ERROR_STOP=1 -c "
  SELECT 'orders' t, count(*) FROM olist.orders
  UNION ALL SELECT 'order_items', count(*) FROM olist.order_items
  UNION ALL SELECT 'customers', count(*) FROM olist.customers
  UNION ALL SELECT 'products', count(*) FROM olist.products
  UNION ALL SELECT 'sellers', count(*) FROM olist.sellers
  UNION ALL SELECT 'payments', count(*) FROM olist.order_payments
  UNION ALL SELECT 'reviews', count(*) FROM olist.order_reviews
  UNION ALL SELECT 'geolocation', count(*) FROM olist.geolocation;"

echo ">> Seed concluído."
