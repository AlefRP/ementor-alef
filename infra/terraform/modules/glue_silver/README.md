# glue_silver

Jobs AWS Glue que materializam a camada silver como Apache Iceberg no Glue
Catalog, usando modelagem Raw Data Vault (hubs, links, satellites e reference
tables — specs declarativas em `src/glue_silver_runtime/`).

- `cold_datavault`: consome os datasets Olist da raw fria (batch).
- `hot_datavault_microbatch`: consome eventos da raw quente em microbatch.

Os scripts ficam versionados no bucket de artefatos em `glue/silver/` (runtime
compartilhado via `--extra-py-files`) e os jobs são agendados por EventBridge.
Falha ou timeout de job publica no tópico SNS `*-silver-glue-failures`
(assinatura de e-mail opcional via `alert_email`).
