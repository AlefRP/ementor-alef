"""Job Glue: eventos de pedido da raw quente -> Raw Data Vault Iceberg na silver."""
from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from hot_specs import EVENT_SCHEMA, EVENT_VAULT, RECORD_SOURCE_PREFIX, achatar_eventos
from iceberg import (
    configurar_iceberg,
    escrever_frame_do_vault,
    garantir_database,
    log_json,
)
from raw import caminho_quente, ler_arquivos_de_evento_json
from vault import montar_frames_do_vault


def argumentos_do_job() -> dict[str, str]:
    """Argumentos do job resolvidos pelo Glue (--raw_bucket, --silver_bucket...)."""
    return getResolvedOptions(
        sys.argv,
        ['JOB_NAME', 'raw_bucket', 'silver_bucket', 'silver_database'],
    )


def main() -> None:
    args = argumentos_do_job()
    sc = SparkContext()
    glue = GlueContext(sc)
    spark = glue.spark_session
    job = Job(glue)
    job.init(args['JOB_NAME'], args)

    configurar_iceberg(spark, args['silver_bucket'])
    garantir_database(spark, args['silver_database'])

    eventos = ler_arquivos_de_evento_json(
        spark,
        caminho_quente(args['raw_bucket']),
        'events',
        EVENT_SCHEMA,
        RECORD_SOURCE_PREFIX,
    )
    for vault_frame in montar_frames_do_vault(achatar_eventos(eventos), EVENT_VAULT):
        escrever_frame_do_vault(vault_frame, args['silver_database'])
    log_json(event='microbatch_done')

    job.commit()


if __name__ == '__main__':
    main()
