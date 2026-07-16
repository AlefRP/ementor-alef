"""Escrita Iceberg dos artefatos Data Vault produzidos pelos jobs silver.

Cada tipo de artefato tem a estratégia de merge que o DV 2.0 pede:
hubs/links são insert-only por hash key; satellites inserem nova versão
quando o ``hashdiff`` difere do registro mais recente da chave (comparar com
a história inteira suprimiria reativações A -> B -> A); references guardam
apenas o estado corrente (upsert).
"""
from __future__ import annotations

import json
import logging

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from vault import VaultFrame

CATALOG = 'glue_catalog'

logger = logging.getLogger('glue_silver')


def registrar_log(**campos) -> None:
    """Log estruturado em JSON (convenção do repo; visível no CloudWatch)."""
    logger.info(json.dumps(campos, default=str))


def configurar_iceberg(spark, silver_bucket: str) -> None:
    """Configura o catálogo Iceberg/Glue; no Glue o --conf do job é quem vale.

    Repetir aqui permite rodar o runtime fora do Glue (testes, Spark local).
    Só entram as configs de catálogo, que são DINÂMICAS (o catálogo é
    instanciado no primeiro uso). ``spark.sql.extensions`` é config ESTÁTICA:
    setá-la numa sessão ativa lança ``Cannot modify the value of a static
    config`` — ela precisa nascer com a sessão (no Glue, o ``--conf`` do job;
    fora dele, ``SparkSession.builder.config``).
    """
    spark.conf.set(
        f'spark.sql.catalog.{CATALOG}',
        'org.apache.iceberg.spark.SparkCatalog',
    )
    spark.conf.set(
        f'spark.sql.catalog.{CATALOG}.catalog-impl',
        'org.apache.iceberg.aws.glue.GlueCatalog',
    )
    spark.conf.set(
        f'spark.sql.catalog.{CATALOG}.io-impl',
        'org.apache.iceberg.aws.s3.S3FileIO',
    )
    spark.conf.set(
        f'spark.sql.catalog.{CATALOG}.warehouse',
        f's3://{silver_bucket}/warehouse/',
    )


def garantir_database(spark, database: str) -> None:
    """Cria o database no catálogo se ainda não existir (idempotente)."""
    spark.sql(f'CREATE DATABASE IF NOT EXISTS {CATALOG}.{database}')


def nome_completo_da_tabela(database: str, table: str) -> str:
    """Nome completo da tabela no catálogo: catalogo.database.tabela."""
    return f'{CATALOG}.{database}.{table}'


def garantir_tabela(df: DataFrame, database: str, table: str) -> None:
    """Cria a tabela Iceberg vazia com o schema do DataFrame (idempotente)."""
    view = f'empty_{table}'
    df.limit(0).createOrReplaceTempView(view)
    df.sparkSession.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {nome_completo_da_tabela(database, table)}
        USING iceberg
        TBLPROPERTIES ('format-version'='2')
        AS SELECT * FROM {view} WHERE 1 = 0
        """  # nosec B608 — identificadores vêm das specs internas, não de input
    )


def condicao_do_merge(keys: list[str]) -> str:
    """Cláusula ON do MERGE: casa alvo (t) e stage (s) por todas as chaves."""
    return ' AND '.join(f't.{key} = s.{key}' for key in keys)


def merge_somente_insere(
    df: DataFrame, database: str, table: str, keys: list[str]
) -> None:
    """Hubs e links: insere apenas hash keys inéditas (histórico imutável)."""
    sem_duplicatas = df.dropDuplicates(keys)
    linhas_no_stage = sem_duplicatas.count()
    if linhas_no_stage == 0:
        return

    garantir_tabela(sem_duplicatas, database, table)
    view = f'stage_{table}'
    sem_duplicatas.createOrReplaceTempView(view)
    sem_duplicatas.sparkSession.sql(
        f"""
        MERGE INTO {nome_completo_da_tabela(database, table)} t
        USING {view} s
        ON {condicao_do_merge(keys)}
        WHEN NOT MATCHED THEN INSERT *
        """  # nosec B608 — identificadores vêm das specs internas, não de input
    )
    registrar_log(event='vault_write', table=table, staged_rows=linhas_no_stage)


def merge_atualiza_ou_insere(
    df: DataFrame, database: str, table: str, keys: list[str]
) -> None:
    """References: upsert — lookup guarda o estado corrente, não histórico."""
    sem_duplicatas = df.dropDuplicates(keys)
    linhas_no_stage = sem_duplicatas.count()
    if linhas_no_stage == 0:
        return

    garantir_tabela(sem_duplicatas, database, table)
    view = f'stage_{table}'
    sem_duplicatas.createOrReplaceTempView(view)
    sem_duplicatas.sparkSession.sql(
        f"""
        MERGE INTO {nome_completo_da_tabela(database, table)} t
        USING {view} s
        ON {condicao_do_merge(keys)}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """  # nosec B608 — identificadores vêm das specs internas, não de input
    )
    registrar_log(event='vault_write', table=table, staged_rows=linhas_no_stage)


def novas_linhas_de_satellite(
    stage: DataFrame, current: DataFrame, hk: str
) -> DataFrame:
    """Mantém as linhas cujo hashdiff difere do registro MAIS RECENTE da chave."""
    mais_recente_primeiro = Window.partitionBy(hk).orderBy(F.col('load_dts').desc())
    ultima_versao = (
        current.withColumn('_rn', F.row_number().over(mais_recente_primeiro))
        .where(F.col('_rn') == 1)
        .select(F.col(hk).alias('_hk'), F.col('hashdiff').alias('_hashdiff'))
    )
    return (
        stage.join(ultima_versao, stage[hk] == ultima_versao['_hk'], 'left')
        .where(F.col('_hashdiff').isNull() | (F.col('hashdiff') != F.col('_hashdiff')))
        .drop('_hk', '_hashdiff')
    )


def merge_de_satellite(df: DataFrame, database: str, table: str, hk: str) -> None:
    """Satellites: insere nova versão quando o hashdiff muda ante a última."""
    sem_duplicatas = df.dropDuplicates([hk, 'hashdiff'])
    garantir_tabela(sem_duplicatas, database, table)
    atual = df.sparkSession.table(nome_completo_da_tabela(database, table))
    novas = novas_linhas_de_satellite(sem_duplicatas, atual, hk)
    linhas_inseridas = novas.count()
    if linhas_inseridas:
        novas.writeTo(nome_completo_da_tabela(database, table)).append()
    registrar_log(event='vault_write', table=table, appended_rows=linhas_inseridas)


def escrever_frame_do_vault(vault_frame: VaultFrame, database: str) -> None:
    """Despacha o VaultFrame para a estratégia de escrita do seu tipo."""
    if vault_frame.kind in ('hub', 'link'):
        merge_somente_insere(
            vault_frame.frame, database, vault_frame.table, vault_frame.keys
        )
    elif vault_frame.kind == 'satellite':
        merge_de_satellite(
            vault_frame.frame, database, vault_frame.table, vault_frame.keys[0]
        )
    elif vault_frame.kind == 'reference':
        merge_atualiza_ou_insere(
            vault_frame.frame, database, vault_frame.table, vault_frame.keys
        )
    else:
        raise ValueError(
            f'tipo de artefato Data Vault desconhecido: {vault_frame.kind}'
        )
