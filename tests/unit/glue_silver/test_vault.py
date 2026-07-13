"""Testes dos builders declarativos do Raw Data Vault (vault.py).

Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

from pyspark.sql import functions as F

from vault import (
    DatasetVaultSpec,
    HubSpec,
    LinkSpec,
    ReferenceSpec,
    SatelliteSpec,
    chave_hash,
    montar_frames_do_vault,
    montar_hub,
    montar_link,
    montar_reference,
    montar_satellite,
    tem_chaves_preenchidas,
)


def _com_metadados(spark, linhas, colunas):
    """Monta um DataFrame de teste já com load_dts e record_source."""
    df = spark.createDataFrame(linhas, colunas)
    return df.withColumn('load_dts', F.current_timestamp()).withColumn(
        'record_source', F.lit('raw.olist.teste')
    )


def test_chave_hash_normaliza_caixa_e_espacos(spark):
    # Arrange
    df = spark.createDataFrame([(' abc ', 'ABC')], ['a', 'b'])

    # Act
    resultado = df.select(
        chave_hash(['a']).alias('hash_a'), chave_hash(['b']).alias('hash_b')
    ).first()

    # Assert
    assert resultado.hash_a == resultado.hash_b


def test_chave_hash_distingue_valores_diferentes(spark):
    # Arrange
    df = spark.createDataFrame([('x', 'y')], ['a', 'b'])

    # Act
    resultado = df.select(
        chave_hash(['a']).alias('hash_a'), chave_hash(['b']).alias('hash_b')
    ).first()

    # Assert
    assert resultado.hash_a != resultado.hash_b


def test_tem_chaves_preenchidas_descarta_linha_sem_chave(spark):
    # Arrange
    df = spark.createDataFrame([('c1',), (None,)], 'k string')

    # Act
    linhas_validas = df.where(tem_chaves_preenchidas(['k'])).count()

    # Assert
    assert linhas_validas == 1


def test_montar_hub_deriva_hash_e_preserva_chave_de_negocio(spark):
    # Arrange
    df = _com_metadados(spark, [('c1',), ('c1',)], ['customer_id'])
    spec = HubSpec('hub_x', 'x_hk', 'customer_id', ['customer_id'])

    # Act
    hub = montar_hub(df, spec)

    # Assert
    assert hub.kind == 'hub'
    assert hub.keys == ['x_hk']
    linhas = hub.frame.collect()
    assert {linha.customer_id for linha in linhas} == {'c1'}
    assert all(len(linha.x_hk) == 64 for linha in linhas)


def test_montar_link_referencia_os_mesmos_hashes_dos_hubs(spark):
    # Arrange
    df = _com_metadados(spark, [('o1', 'c1')], ['order_id', 'customer_id'])
    spec_do_hub = HubSpec(
        'hub_customer_account', 'customer_account_hk', 'customer_id', ['customer_id']
    )
    spec_do_link = LinkSpec(
        'link_order_customer',
        'link_order_customer_hk',
        ['order_id', 'customer_id'],
        {'order_hk': ['order_id'], 'customer_account_hk': ['customer_id']},
    )

    # Act
    hub = montar_hub(df, spec_do_hub)
    link = montar_link(df, spec_do_link)

    # Assert
    assert link.kind == 'link'
    assert (
        link.frame.first().customer_account_hk == hub.frame.first().customer_account_hk
    )


def test_montar_satellite_versiona_contexto_por_hashdiff(spark):
    # Arrange
    df = _com_metadados(spark, [('c1', 'SP'), ('c1', 'RJ')], ['customer_id', 'state'])
    spec = SatelliteSpec('sat_x', 'x_hk', ['customer_id'], ['state'])

    # Act
    satellite = montar_satellite(df, spec)

    # Assert
    assert satellite.kind == 'satellite'
    linhas = satellite.frame.collect()
    assert len({linha.x_hk for linha in linhas}) == 1
    assert len({linha.hashdiff for linha in linhas}) == 2


def test_montar_reference_mantem_chave_natural_sem_hash(spark):
    # Arrange
    df = _com_metadados(spark, [('pet_shop', 'pet_shop_en')], ['nome', 'nome_en'])
    spec = ReferenceSpec('ref_x', ['nome'], ['nome_en'])

    # Act
    reference = montar_reference(df, spec)

    # Assert
    assert reference.kind == 'reference'
    assert reference.keys == ['nome']
    linha = reference.frame.first()
    assert (linha.nome, linha.nome_en) == ('pet_shop', 'pet_shop_en')


def test_montar_reference_aplica_prepare(spark):
    # Arrange
    df = _com_metadados(spark, [('a', 'x'), ('b', None)], ['nome', 'valor'])
    spec = ReferenceSpec(
        'ref_x',
        ['nome'],
        ['valor'],
        prepare=lambda frame: frame.where(F.col('valor').isNotNull()),
    )

    # Act
    reference = montar_reference(df, spec)

    # Assert
    assert reference.frame.count() == 1


def test_montar_frames_do_vault_produz_todos_os_tipos(spark):
    # Arrange
    df = _com_metadados(spark, [('k1', 'v1')], ['k', 'v'])
    spec = DatasetVaultSpec(
        hubs=[HubSpec('h', 'h_hk', 'k', ['k'])],
        links=[LinkSpec('l', 'l_hk', ['k'], {'h_hk': ['k']})],
        satellites=[SatelliteSpec('s', 'h_hk', ['k'], ['v'])],
        references=[ReferenceSpec('r', ['k'], ['v'])],
    )

    # Act
    frames = montar_frames_do_vault(df, spec)

    # Assert
    assert [frame.kind for frame in frames] == ['hub', 'link', 'satellite', 'reference']
