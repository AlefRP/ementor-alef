"""Job Glue: datasets Olist da raw fria -> Raw Data Vault Iceberg na silver."""
from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from cold_specs import DATASETS, RECORD_SOURCE_PREFIX, datasets_selecionados
from iceberg import (
    configurar_iceberg,
    escrever_frame_do_vault,
    garantir_database,
    log_json,
)
from raw import caminho_frio, ler_arquivos_de_lote_json
from vault import montar_frames_do_vault


def argumentos_do_job() -> dict[str, str]:
    """Argumentos do job resolvidos pelo Glue (--raw_bucket, --datasets...)."""
    return getResolvedOptions(
        sys.argv,
        ['JOB_NAME', 'raw_bucket', 'silver_bucket', 'silver_database', 'datasets'],
    )


def processar_dataset(spark, dataset: str, raw_bucket: str, database: str) -> None:
    """Um dataset, três passos: ler da raw -> modelar o vault -> escrever."""
    spec = DATASETS[dataset]
    df_da_raw = ler_arquivos_de_lote_json(
        spark,
        caminho_frio(raw_bucket, dataset),
        dataset,
        spec.schema,
        RECORD_SOURCE_PREFIX,
    )
    for vault_frame in montar_frames_do_vault(df_da_raw, spec.vault):
        escrever_frame_do_vault(vault_frame, database)


def main() -> None:
    args = argumentos_do_job()
    sc = SparkContext()
    glue = GlueContext(sc)
    spark = glue.spark_session
    job = Job(glue)
    job.init(args['JOB_NAME'], args)

    configurar_iceberg(spark, args['silver_bucket'])
    garantir_database(spark, args['silver_database'])

    # Datasets são independentes: um lote ruim não derruba os demais; o job
    # falha no fim para o alerta disparar e a execução ficar vermelha.
    falhas: list[str] = []
    for dataset in datasets_selecionados(args['datasets']):
        try:
            processar_dataset(
                spark, dataset, args['raw_bucket'], args['silver_database']
            )
            log_json(event='dataset_done', dataset=dataset)
        except Exception as erro:  # noqa: BLE001 — reportado e re-levantado no fim
            falhas.append(dataset)
            log_json(event='dataset_failed', dataset=dataset, error=str(erro))

    job.commit()
    if falhas:
        raise RuntimeError(f'datasets com falha: {", ".join(falhas)}')


if __name__ == '__main__':
    main()
