# Módulo database

RDS PostgreSQL 16 (`db.t4g.micro`, gp3 20 GB) — sistema de origem do lakehouse,
que recebe o dataset **Olist** (e-commerce brasileiro) em carga única via
`scripts/database/`.

Segurança:
- subnets privadas + `publicly_accessible = false`;
- ingress 5432 apenas do SG da API (módulo `network`);
- `storage_encrypted` + senha master gerenciada pela AWS no **Secrets Manager**
  (`manage_master_user_password` — sem segredo no código ou state).

Trade-offs de mentoria (documentados no código com `checkov:skip`): single-AZ,
sem deletion protection e sem snapshot final — o dataset é recarregável.
