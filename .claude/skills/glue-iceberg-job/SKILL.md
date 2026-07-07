---
name: glue-iceberg-job
description: >-
  Use ao escrever ou otimizar jobs AWS Glue / PySpark que transformam a camada
  raw em silver (Apache Iceberg) no lakehouse — leitura de S3, transformações,
  escrita Iceberg via catálogo Lake Formation, particionamento e tuning de
  performance. Acione em "job Glue", "PySpark", "raw para silver", "Iceberg",
  "microbatch", "otimizar Spark".
---

# Job Glue + PySpark + Iceberg (raw → silver)

Fonte: docs oficiais PySpark (Best Practices) + *Fundamentals of Data Engineering*
(undercurrents: DataOps, orquestração, qualidade). Este repo usa GlueContext +
DynamicFrame e Iceberg via catálogo Lake Formation.

## Estrutura obrigatória de um job

1. **Boilerplate Glue**: `getResolvedOptions`, `SparkContext`, `GlueContext`, `Job.init/commit`.
2. **Schema explícito e validado** — nunca confie em inferência para produção.
3. **Idempotência** — reprocessar a mesma partição não duplica dados (Iceberg `MERGE`/overwrite de partição).
4. **Logging estruturado** + tratamento de erro em cada estágio (leitura/transformação/escrita).
5. **`job.commit()`** ao final (bookmarks).

```python
import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

args = getResolvedOptions(sys.argv, ["JOB_NAME", "raw_path", "silver_table"])
sc = SparkContext()
glue = GlueContext(sc)
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

# ... leitura raw -> transformação -> escrita silver (Iceberg) ...

job.commit()
```

## Iceberg via Lake Formation (configuração Spark)

```python
spark.conf.set("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.catalog-impl",
               "org.apache.iceberg.aws.glue.GlueCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.warehouse", args["silver_table"])
spark.conf.set("spark.sql.extensions",
               "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
```

## Performance (checklist PySpark — aplique)

- **Partition pruning**: particione silver por `year/month/day` e sempre filtre por essas colunas (a convenção de path do repo). Filtro só em coluna não-particionada lê tudo.
- **Broadcast join** para tabelas pequenas (< ~100 MB): `broadcast(df_dim)`.
- **Evite UDFs** quando houver função nativa (Catalyst otimiza colunas inteiras; UDF processa linha a linha).
- **Tamanho de arquivo alvo 128 MB–1 GB** por arquivo — evite o *small files problem* (use `coalesce`/`repartition` ou compaction do Iceberg).
- **Memory overhead 20–25%** para PySpark (Arrow/pandas UDF alocam memória nativa fora do JVM).
- **`DataFrame.explain()`** antes de rodar transformação cara (execução preguiçosa).
- **Cache** só o que é reutilizado; libere com `unpersist()`.

## Convenções do repo (undercurrents)

- Path S3 **sempre** particionado por `year/month/day`.
- Código de produção em `src/` (ex.: `src/cold/`, `src/hot/`); teste em `tests/`.
- Logging estruturado (JSON) — nada de `print`. Inclua `job_name`, `partition`, `row_count`.
- Trate falhas parciais: registre a partição problemática e falhe explicitamente (não engula exceção).
- Segurança: sem credenciais no código — a role do Glue (ver `lakehouse-governance`) já dá acesso a raw/silver.

## Erros comuns (evite)

- ❌ `inferSchema` em produção → schema drift silencioso.
- ❌ Escrever milhares de arquivos pequenos por microbatch.
- ❌ `df.collect()` em dataset grande (traz tudo pro driver → OOM).
- ❌ Filtrar por coluna não-particionada esperando pruning.
- ❌ Esquecer `job.commit()` (bookmarks e idempotência quebram).

Ver também: `lakehouse-governance` (role do Glue), `aws-lambda-ingestion` (produz a raw),
`pytest`/agent `data-engineer` para testes.
