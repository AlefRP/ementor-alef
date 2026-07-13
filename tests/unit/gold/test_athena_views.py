"""Testes do DDL da camada gold e das queries da camada consumer.

Não tocam a AWS: validam o CONTRATO dos arquivos .sql — que eles renderizam sem
placeholder solto, que cada view nasce no database gold e, sobretudo, que o
consumer consome a GOLD (nunca a silver direto, o que fura a camada).
"""
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / 'scripts' / 'athena'))

from apply_views import arquivos_de_ddl, renderizar  # noqa: E402

CONSUMER = RAIZ / 'src' / 'consumer'

SILVER = 'silver_datavault'
GOLD = 'gold'


def _consultas_do_consumer():
    return sorted(CONSUMER.glob('*.sql'))


def test_ddl_da_gold_cobre_as_duas_camadas():
    # Arrange / Act
    arquivos = arquivos_de_ddl()

    # Assert — o desenho pede views de gold na fria E na quente.
    camadas = {arquivo.parent.parent.name for arquivo in arquivos}
    assert arquivos, 'esperava DDL da gold em src/{cold,hot}/athena_gold'
    assert camadas == {'cold', 'hot'}


@pytest.mark.parametrize('arquivo', arquivos_de_ddl(), ids=lambda p: p.name)
def test_view_da_gold_renderiza_e_nasce_no_database_gold(arquivo):
    # Arrange
    sql = arquivo.read_text(encoding='utf-8')

    # Act
    renderizado = renderizar(sql, SILVER, GOLD)

    # Assert
    assert '${' not in renderizado, 'placeholder não substituído no DDL'
    assert re.search(
        rf'CREATE OR REPLACE VIEW\s+{GOLD}\.\w+', renderizado
    ), 'a view precisa ser criada no database gold'


@pytest.mark.parametrize('arquivo', arquivos_de_ddl(), ids=lambda p: p.name)
def test_view_da_gold_e_idempotente(arquivo):
    # Arrange / Act
    sql = arquivo.read_text(encoding='utf-8')

    # Assert — CREATE VIEW puro quebraria na segunda aplicação da esteira.
    assert 'CREATE OR REPLACE VIEW' in sql
    assert not re.search(r'CREATE\s+VIEW\s', sql)


def test_nomes_das_views_nao_colidem():
    # Arrange
    nomes = []

    # Act
    for arquivo in arquivos_de_ddl():
        sql = renderizar(arquivo.read_text(encoding='utf-8'), SILVER, GOLD)
        nomes.extend(re.findall(rf'CREATE OR REPLACE VIEW\s+{GOLD}\.(\w+)', sql))

    # Assert — duas views com o mesmo nome: a última aplicada venceria em silêncio.
    assert len(nomes) == len(set(nomes)), f'nomes de view duplicados: {nomes}'


@pytest.mark.parametrize('consulta', _consultas_do_consumer(), ids=lambda p: p.name)
def test_consumer_consulta_a_gold_e_nao_a_silver(consulta):
    # Arrange
    sql = consulta.read_text(encoding='utf-8')

    # Act
    renderizado = renderizar(sql, SILVER, GOLD)

    # Assert — a camada consumer existe para consumir a gold; ler a silver direto
    # (hub_/link_/sat_) devolveria o Data Vault cru ao usuário final.
    assert '${' not in renderizado
    assert SILVER not in renderizado, 'consumer não deve ler a silver direto'
    assert f'{GOLD}.' in renderizado, 'consumer deve consultar as views da gold'
    assert not re.search(
        r'\b(hub|link|sat)_\w+', renderizado
    ), 'consumer não deve referenciar tabelas cruas do Data Vault'


def test_consumer_tem_consulta_das_duas_camadas():
    # Arrange / Act
    consultas = _consultas_do_consumer()
    corpo = '\n'.join(c.read_text(encoding='utf-8') for c in consultas)

    # Assert — consumo analítico das duas pontas do desenho.
    assert consultas, 'esperava queries analíticas em src/consumer'
    assert 'fact_order_item' in corpo, 'sem consulta sobre a gold da camada fria'
    assert 'fact_order_event' in corpo, 'sem consulta sobre a gold da camada quente'
