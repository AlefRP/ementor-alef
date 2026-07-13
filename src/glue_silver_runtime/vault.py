"""Construtor declarativo de Data Vault para DataFrames Spark.

Raw Data Vault (DV 2.0, Linstedt): o hub guarda a chave de negócio, o link
guarda o relacionamento entre hubs (com dependent child keys quando preciso)
e o satellite guarda o contexto descritivo, versionado por ``hashdiff``.
Reference tables atendem lookups descritivos que não são objetos de negócio.
As specs são declarativas; os builders derivam DataFrames prontos para a
escrita idempotente (ver ``iceberg.py``).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

VaultKind = Literal['hub', 'link', 'satellite', 'reference']


@dataclass(frozen=True)
class HubSpec:
    """Hub: uma linha por chave de negócio, identificada por hash key."""

    table: str
    hk: str
    business_key: str
    key_cols: list[str]


@dataclass(frozen=True)
class LinkSpec:
    """Link: relacionamento entre hubs; ``attrs`` são dependent child keys."""

    table: str
    hk: str
    key_cols: list[str]
    hubs: dict[str, list[str]]
    attrs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SatelliteSpec:
    """Satellite: contexto descritivo do pai, versionado por hashdiff."""

    table: str
    parent_hk: str
    parent_key_cols: list[str]
    attrs: list[str]


@dataclass(frozen=True)
class ReferenceSpec:
    """Reference table: lookup descritivo, sem hash key (estado corrente)."""

    table: str
    key_cols: list[str]
    attrs: list[str]
    prepare: Callable[[DataFrame], DataFrame] | None = None


@dataclass(frozen=True)
class DatasetVaultSpec:
    hubs: list[HubSpec] = field(default_factory=list)
    links: list[LinkSpec] = field(default_factory=list)
    satellites: list[SatelliteSpec] = field(default_factory=list)
    references: list[ReferenceSpec] = field(default_factory=list)


@dataclass(frozen=True)
class VaultFrame:
    """DataFrame pronto para escrita + como escrevê-lo (tipo e chaves)."""

    kind: VaultKind
    table: str
    frame: DataFrame
    keys: list[str]


def colunas_normalizadas(cols: Iterable[str]) -> list[Column]:
    """Normaliza colunas antes do hash: trim + caixa alta + nulo vira ''.

    Garante que ' abc ' e 'ABC' produzam a MESMA hash key (padrão DV 2.0).
    """
    return [
        F.coalesce(F.upper(F.trim(F.col(col).cast('string'))), F.lit(''))
        for col in cols
    ]


def chave_hash(cols: Iterable[str]) -> Column:
    """Hash SHA-256 da(s) chave(s) de negócio, com '||' de separador."""
    return F.sha2(F.concat_ws('||', *colunas_normalizadas(cols)), 256)


def hash_dos_atributos(cols: Iterable[str]) -> Column:
    """Mesmo cálculo da chave_hash, sobre os ATRIBUTOS: detecta mudança."""
    return chave_hash(cols)


def tem_chaves_preenchidas(cols: Iterable[str]) -> Column:
    """Condição 'todas as chaves presentes' — linha sem chave não entra."""
    condicao = F.lit(True)
    for col in cols:
        condicao = condicao & F.col(col).isNotNull()
    return condicao


def montar_hub(df: DataFrame, spec: HubSpec) -> VaultFrame:
    """Hub = hash key + chave de negócio + metadados de carga."""
    frame = df.where(tem_chaves_preenchidas(spec.key_cols)).select(
        chave_hash(spec.key_cols).alias(spec.hk),
        F.col(spec.business_key),
        'load_dts',
        'record_source',
    )
    return VaultFrame('hub', spec.table, frame, [spec.hk])


def montar_link(df: DataFrame, spec: LinkSpec) -> VaultFrame:
    """Link = hash do relacionamento + hash de cada hub participante."""
    colunas = [chave_hash(spec.key_cols).alias(spec.hk)]
    colunas.extend(chave_hash(cols).alias(hk) for hk, cols in spec.hubs.items())
    colunas.extend(F.col(col) for col in spec.attrs)
    colunas.extend([F.col('load_dts'), F.col('record_source')])
    frame = df.where(tem_chaves_preenchidas(spec.key_cols)).select(*colunas)
    return VaultFrame('link', spec.table, frame, [spec.hk])


def montar_satellite(df: DataFrame, spec: SatelliteSpec) -> VaultFrame:
    """Satellite = hash do pai + atributos + hashdiff (versão do contexto)."""
    colunas = [chave_hash(spec.parent_key_cols).alias(spec.parent_hk)]
    colunas.extend(F.col(col) for col in spec.attrs)
    colunas.extend(
        [
            hash_dos_atributos(spec.attrs).alias('hashdiff'),
            F.col('load_dts'),
            F.col('record_source'),
        ]
    )
    frame = df.where(tem_chaves_preenchidas(spec.parent_key_cols)).select(*colunas)
    return VaultFrame('satellite', spec.table, frame, [spec.parent_hk])


def montar_reference(df: DataFrame, spec: ReferenceSpec) -> VaultFrame:
    """Reference = chave natural + atributos, sem hash (estado corrente)."""
    origem = spec.prepare(df) if spec.prepare else df
    frame = origem.where(tem_chaves_preenchidas(spec.key_cols)).select(
        *[F.col(col) for col in spec.key_cols],
        *[F.col(col) for col in spec.attrs],
        F.col('load_dts'),
        F.col('record_source'),
    )
    return VaultFrame('reference', spec.table, frame, list(spec.key_cols))


def montar_frames_do_vault(df: DataFrame, spec: DatasetVaultSpec) -> list[VaultFrame]:
    """Aplica a spec inteira de um dataset: todos os frames prontos p/ escrita."""
    frames: list[VaultFrame] = []
    frames.extend(montar_hub(df, hub) for hub in spec.hubs)
    frames.extend(montar_link(df, link) for link in spec.links)
    frames.extend(montar_satellite(df, sat) for sat in spec.satellites)
    frames.extend(montar_reference(df, ref) for ref in spec.references)
    return frames
