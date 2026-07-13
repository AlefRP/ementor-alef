"""Testes do mapeamento Data Vault dos datasets frios (Olist).

Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

from pyspark.sql import functions as F

from cold_specs import DATASETS, datasets_selecionados
from vault import montar_frames_do_vault

TABELAS_OLIST = {
    'customers',
    'sellers',
    'products',
    'orders',
    'order_items',
    'order_payments',
    'order_reviews',
    'geolocation',
    'product_category_name_translation',
}


def _com_metadados(spark, linhas, colunas):
    """Monta um DataFrame de teste já com load_dts e record_source."""
    df = spark.createDataFrame(linhas, colunas)
    return df.withColumn('load_dts', F.current_timestamp()).withColumn(
        'record_source', F.lit('raw.olist.teste')
    )


def test_datasets_selecionados_all_retorna_todos():
    # Arrange
    entrada = 'all'

    # Act
    selecionados = datasets_selecionados(entrada)

    # Assert
    assert selecionados == list(DATASETS)


def test_datasets_selecionados_lista_ignora_espacos():
    # Arrange
    entrada = ' orders , customers '

    # Act
    selecionados = datasets_selecionados(entrada)

    # Assert
    assert selecionados == ['orders', 'customers']


def test_datasets_cobrem_todas_as_tabelas_olist():
    # Arrange / Act
    datasets_mapeados = set(DATASETS)

    # Assert
    assert datasets_mapeados == TABELAS_OLIST


def test_hub_customer_usa_chave_de_negocio_verdadeira():
    # Arrange
    vault = DATASETS['customers'].vault

    # Act
    hubs = {hub.table: hub for hub in vault.hubs}
    links = [link.table for link in vault.links]

    # Assert — customer_id é 1-por-pedido; a identidade é customer_unique_id
    assert hubs['hub_customer'].business_key == 'customer_unique_id'
    assert hubs['hub_customer_account'].business_key == 'customer_id'
    assert 'link_customer_account' in links


def test_categoria_e_geolocalizacao_sao_reference_tables():
    # Arrange
    categoria = DATASETS['product_category_name_translation'].vault
    geolocalizacao = DATASETS['geolocation'].vault

    # Act / Assert — lookups descritivos não viram hub nem link
    assert not categoria.hubs and not categoria.links
    assert categoria.references[0].table == 'ref_product_category'
    assert not geolocalizacao.hubs
    assert geolocalizacao.references[0].prepare is not None


def test_customers_integra_contas_no_mesmo_cliente(spark):
    # Arrange — duas contas (pedidos) do MESMO cliente u1
    df = _com_metadados(
        spark,
        [
            ('acc1', 'u1', '01310', 'sao paulo', 'SP'),
            ('acc2', 'u1', '01310', 'sao paulo', 'SP'),
        ],
        [
            'customer_id',
            'customer_unique_id',
            'customer_zip_code_prefix',
            'customer_city',
            'customer_state',
        ],
    )

    # Act
    frames = {
        frame.table: frame
        for frame in montar_frames_do_vault(df, DATASETS['customers'].vault)
    }

    # Assert — as contas convergem num só hub_customer via same-as link
    assert set(frames) == {
        'hub_customer',
        'hub_customer_account',
        'link_customer_account',
        'sat_customer_profile',
    }
    assert frames['hub_customer'].frame.dropDuplicates(['customer_hk']).count() == 1
    contas_distintas = (
        frames['hub_customer_account'].frame.select('customer_account_hk').distinct()
    )
    assert contas_distintas.count() == 2
    assert frames['link_customer_account'].frame.count() == 2


def test_ref_geolocation_agrega_centroide_por_prefixo(spark):
    # Arrange — dois pontos do mesmo prefixo de CEP
    df = _com_metadados(
        spark,
        [
            (1, '01310', 1.0, 10.0, 'sao paulo', 'SP'),
            (2, '01310', 3.0, 30.0, 'sao paulo', 'SP'),
        ],
        [
            'geolocation_id',
            'geolocation_zip_code_prefix',
            'geolocation_lat',
            'geolocation_lng',
            'geolocation_city',
            'geolocation_state',
        ],
    )

    # Act
    frames = montar_frames_do_vault(df, DATASETS['geolocation'].vault)

    # Assert — vira UMA linha por prefixo, com a média das coordenadas
    reference = frames[0]
    assert reference.table == 'ref_geolocation'
    linhas = reference.frame.collect()
    assert len(linhas) == 1
    assert linhas[0].geolocation_lat == 2.0
    assert linhas[0].geolocation_lng == 20.0
