#!/usr/bin/env python3
"""Roda uma query analítica da camada consumer no Athena e imprime o resultado.

A camada consumer é o ponto final do desenho: consulta analítica sobre a gold.
As queries vivem versionadas em ``src/consumer/*.sql`` e usam o mesmo placeholder
``${gold_database}`` das views — o script resolve o nome pelos outputs do
Terraform, então o mesmo SQL roda em qualquer ambiente.

Uso:
    python scripts/athena/run_query.py --tf-dir infra/terraform/environments/prod \\
        --query 01_receita_por_categoria
    python scripts/athena/run_query.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Reusa a resolução de alvos e a espera de execução do aplicador das views.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_views import (  # noqa: E402
    AJUDA_SOBRESCREVE,
    ROOT,
    _dizer,
    _executar,
    _resolver_alvos,
    renderizar,
)

CONSULTAS = ROOT / 'src' / 'consumer'
MAX_LINHAS = 100


def _consultas_disponiveis() -> list[Path]:
    return sorted(CONSULTAS.glob('*.sql'))


def _resolver_consulta(nome: str) -> Path:
    """Aceita o nome com ou sem a extensão .sql."""
    caminho = CONSULTAS / (nome if nome.endswith('.sql') else f'{nome}.sql')
    if not caminho.exists():
        disponiveis = ', '.join(p.stem for p in _consultas_disponiveis())
        raise SystemExit(f'consulta "{nome}" nao existe. Disponiveis: {disponiveis}')
    return caminho


def _imprimir_resultado(athena, execucao: str) -> None:
    """Imprime as primeiras linhas do resultado como tabela simples."""
    pagina = athena.get_query_results(QueryExecutionId=execucao, MaxResults=MAX_LINHAS)
    linhas = pagina['ResultSet']['Rows']
    if not linhas:
        _dizer('consulta sem resultados')
        return
    for linha in linhas:
        campos = [celula.get('VarCharValue', '') for celula in linha['Data']]
        print(' | '.join(campos))


def _interpretar_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tf-dir', help='environment do terraform (lê os outputs)')
    parser.add_argument('--query', help='nome do arquivo em src/consumer (sem .sql)')
    parser.add_argument('--gold-database', help=AJUDA_SOBRESCREVE)
    parser.add_argument('--silver-database', help=AJUDA_SOBRESCREVE)
    parser.add_argument('--workgroup', help=AJUDA_SOBRESCREVE)
    parser.add_argument(
        '--list', action='store_true', help='lista as consultas disponiveis'
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _interpretar_args(argv)
    if args.list or not args.query:
        _dizer('consultas em src/consumer:')
        for consulta in _consultas_disponiveis():
            print(f'  {consulta.stem}')
        return 0 if args.list else 1

    caminho = _resolver_consulta(args.query)
    silver, gold, workgroup = _resolver_alvos(args)
    sql = renderizar(caminho.read_text(encoding='utf-8'), silver, gold)

    try:
        athena = boto3.client('athena')
        execucao = _executar(athena, sql, workgroup, caminho.name)
        _imprimir_resultado(athena, execucao)
        return 0
    except (BotoCoreError, ClientError, RuntimeError, TimeoutError) as erro:
        _dizer(f'ERRO ao consultar a gold: {erro}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
