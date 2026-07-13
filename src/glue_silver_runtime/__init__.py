"""Runtime compartilhado dos jobs Glue da silver.

Mapa de leitura (cada módulo tem uma responsabilidade):
- ``raw.py``       — LER os arquivos JSON da camada raw (S3) com metadados.
- ``vault.py``     — MODELAR: transforma linhas em hubs/links/satellites/refs.
- ``iceberg.py``   — ESCREVER: merge idempotente de cada tipo em Iceberg.
- ``cold_specs.py``/``hot_specs.py`` — CONFIGURAR: schema + mapeamento Data
  Vault de cada dataset, de forma declarativa (dados, não lógica).

Os jobs em ``src/cold/glue_silver`` e ``src/hot/glue_silver_microbatch`` só
orquestram: ler -> modelar -> escrever.
"""
