"""Leitores da raw (S3) para os jobs Glue da silver."""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StringType, StructField, StructType


def caminho_frio(bucket: str, dataset: str) -> str:
    """Glob S3 dos lotes de um dataset frio, varrendo todas as partições."""
    return f's3://{bucket}/{dataset}/year=*/month=*/day=*/*.json'


def caminho_quente(bucket: str, dataset: str = 'events') -> str:
    """Glob S3 dos eventos quentes, varrendo todas as partições."""
    return f's3://{bucket}/{dataset}/year=*/month=*/day=*/*.json'


def glob_tem_arquivos(spark, caminho: str) -> bool:
    """Existe algum arquivo casando o glob?

    Num ambiente recém-aplicado a raw ainda não recebeu ingestão; ler o glob
    vazio faria ``spark.read`` levantar ``Path does not exist`` e derrubar o
    dataset. Consultamos o FileSystem do Hadoop (mesmo do ``spark.read``) antes
    de ler para, sem arquivos, seguir com um frame vazio em vez de falhar.
    """
    sc = spark.sparkContext
    fs_path = sc._jvm.org.apache.hadoop.fs.Path(caminho)
    fs = fs_path.getFileSystem(sc._jsc.hadoopConfiguration())
    correspondencias = fs.globStatus(fs_path)
    return correspondencias is not None and len(correspondencias) > 0


def _frame_vazio(spark, schema: StructType) -> DataFrame:
    """DataFrame sem linhas com o schema da fonte + a coluna ``raw_file``.

    Mesmo formato do caminho com dados (antes dos metadados de carga), para a
    raw vazia percorrer o mesmo pipeline e materializar a tabela vazia.
    """
    colunas = StructType([StructField('raw_file', StringType(), True), *schema.fields])
    return spark.createDataFrame([], colunas)


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
    """Lê arquivos contendo um array JSON por arquivo (lotes da camada fria).

    Sem arquivos no glob (raw ainda não populada), devolve um frame vazio com o
    schema esperado — o dataset segue e materializa a tabela vazia.
    """
    if glob_tem_arquivos(spark, caminho):
        bruto = spark.read.text(caminho)
        interpretado = bruto.select(
            F.input_file_name().alias('raw_file'),
            F.explode(F.from_json('value', ArrayType(schema))).alias('row'),
        )
        linhas = interpretado.select('raw_file', 'row.*')
    else:
        linhas = _frame_vazio(spark, schema)
    return anexar_metadados_da_raw(linhas, nome_da_fonte, prefixo_record_source)


def ler_arquivos_de_evento_json(
    spark,
    caminho: str,
    nome_da_fonte: str,
    schema: StructType,
    prefixo_record_source: str,
) -> DataFrame:
    """Lê arquivos com um objeto JSON por arquivo (eventos da camada quente).

    Sem arquivos no glob (raw ainda não populada), devolve um frame vazio com o
    schema esperado — o dataset segue e materializa a tabela vazia.
    """
    if glob_tem_arquivos(spark, caminho):
        linhas = spark.read.schema(schema).json(caminho)
        linhas = linhas.withColumn('raw_file', F.input_file_name())
    else:
        linhas = _frame_vazio(spark, schema)
    return anexar_metadados_da_raw(linhas, nome_da_fonte, prefixo_record_source)
