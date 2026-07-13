"""Leitores da raw (S3) para os jobs Glue da silver."""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StructType


def caminho_frio(bucket: str, dataset: str) -> str:
    """Glob S3 dos lotes de um dataset frio, varrendo todas as partições."""
    return f's3://{bucket}/{dataset}/year=*/month=*/day=*/*.json'


def caminho_quente(bucket: str, dataset: str = 'events') -> str:
    """Glob S3 dos eventos quentes, varrendo todas as partições."""
    return f's3://{bucket}/{dataset}/year=*/month=*/day=*/*.json'


def anexar_metadados_da_raw(
    df: DataFrame, nome_da_fonte: str, prefixo_record_source: str
) -> DataFrame:
    """Anexa a cada linha de onde ela veio: partição de origem (extraída do
    caminho do arquivo), momento da carga (load_dts) e fonte (record_source).
    """
    return df.withColumns(
        {
            'raw_year': F.regexp_extract('raw_file', r'year=(\d{4})', 1),
            'raw_month': F.regexp_extract('raw_file', r'month=(\d{2})', 1),
            'raw_day': F.regexp_extract('raw_file', r'day=(\d{2})', 1),
            'raw_partition_date': F.to_date(
                F.concat_ws('-', 'raw_year', 'raw_month', 'raw_day')
            ),
            'load_dts': F.current_timestamp(),
            'record_source': F.lit(f'{prefixo_record_source}.{nome_da_fonte}'),
        }
    )


def ler_arquivos_de_lote_json(
    spark,
    caminho: str,
    nome_da_fonte: str,
    schema: StructType,
    prefixo_record_source: str,
) -> DataFrame:
    """Lê arquivos contendo um array JSON por arquivo (lotes da camada fria)."""
    bruto = spark.read.text(caminho)
    interpretado = bruto.select(
        F.input_file_name().alias('raw_file'),
        F.explode(F.from_json('value', ArrayType(schema))).alias('row'),
    )
    linhas = interpretado.select('raw_file', 'row.*')
    return anexar_metadados_da_raw(linhas, nome_da_fonte, prefixo_record_source)


def ler_arquivos_de_evento_json(
    spark,
    caminho: str,
    nome_da_fonte: str,
    schema: StructType,
    prefixo_record_source: str,
) -> DataFrame:
    """Lê arquivos com um objeto JSON por arquivo (eventos da camada quente)."""
    linhas = spark.read.schema(schema).json(caminho)
    linhas = linhas.withColumn('raw_file', F.input_file_name())
    return anexar_metadados_da_raw(linhas, nome_da_fonte, prefixo_record_source)
