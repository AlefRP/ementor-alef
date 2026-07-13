#!/usr/bin/env python3
"""Aplica o DDL da camada gold (views do Athena) sobre a silver.

As views são CÓDIGO, não infraestrutura: o DDL vive versionado em
``src/{cold,hot}/athena_gold/*.sql`` e é aplicado por este script com
``CREATE OR REPLACE VIEW`` (idempotente — rodar duas vezes é inofensivo).

Por que não pelo Terraform: uma view do Athena só existe no catálogo Glue como
tabela ``VIRTUAL_VIEW`` cujo corpo é um JSON Presto codificado em base64. Modelar
isso em HCL troca um SQL legível e revisável por um blob opaco no state — e o
diff do PR deixaria de mostrar a regra de negócio que mudou.

Ordem importa: os arquivos são aplicados em ordem alfabética dentro de cada
camada (fria antes da quente), e o prefixo numérico existe para que uma view que
depende de outra (``agg_order_event_hourly`` -> ``fact_order_event``) venha
depois. Os nomes de database entram por substituição de ``${silver_database}`` e
``${gold_database}``, então o mesmo DDL serve a qualquer ambiente.

Uso:
    python scripts/athena/apply_views.py --tf-dir infra/terraform/environments/prod
    python scripts/athena/apply_views.py --dry-run --silver-database s --gold-database g
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from string import Template

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[2]

# Fria antes da quente: a quente não depende da fria hoje, mas a ordem deixa o
# log de aplicação na mesma sequência do desenho da arquitetura.
DIRETORIOS_DE_DDL = (
    ROOT / 'src' / 'cold' / 'athena_gold',
    ROOT / 'src' / 'hot' / 'athena_gold',
)

ESTADOS_FINAIS = {'SUCCEEDED', 'FAILED', 'CANCELLED'}
INTERVALO_DE_POLLING = 2
TIMEOUT_SEGUNDOS = 300

AJUDA_SOBRESCREVE = 'sobrescreve o output do terraform'


def _dizer(mensagem: str) -> None:
    print(f'>> {mensagem}', flush=True)


def arquivos_de_ddl() -> list[Path]:
    """DDLs das duas camadas, em ordem alfabética dentro de cada uma."""
    arquivos: list[Path] = []
    for diretorio in DIRETORIOS_DE_DDL:
        arquivos.extend(sorted(diretorio.glob('*.sql')))
    return arquivos


def renderizar(sql: str, silver_database: str, gold_database: str) -> str:
    """Substitui os placeholders de database no DDL."""
    return Template(sql).substitute(
        silver_database=silver_database, gold_database=gold_database
    )


def _saidas_do_terraform(tf_dir: str) -> dict:
    """Lê os outputs do environment (fonte única dos nomes de database)."""
    resultado = subprocess.run(
        ['terraform', f'-chdir={tf_dir}', 'output', '-json'],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(resultado.stdout)


def _executar(athena, sql: str, workgroup: str, nome: str) -> str:
    """Roda um SQL no Athena, espera terminar e devolve o id da execução.

    Erro vira exceção — quem chama não precisa checar estado. O id serve a quem
    quer os resultados depois (ver scripts/athena/run_query.py).
    """
    execucao = athena.start_query_execution(
        QueryString=sql, WorkGroup=workgroup
    )['QueryExecutionId']

    limite = time.monotonic() + TIMEOUT_SEGUNDOS
    while True:
        detalhe = athena.get_query_execution(QueryExecutionId=execucao)
        estado = detalhe['QueryExecution']['Status']['State']
        if estado in ESTADOS_FINAIS:
            break
        if time.monotonic() > limite:
            raise TimeoutError(f'{nome}: {TIMEOUT_SEGUNDOS}s sem concluir ({estado})')
        time.sleep(INTERVALO_DE_POLLING)

    if estado != 'SUCCEEDED':
        motivo = detalhe['QueryExecution']['Status'].get(
            'StateChangeReason', 'sem detalhe'
        )
        raise RuntimeError(f'{nome}: {estado} - {motivo}')
    _dizer(f'{nome}: OK')
    return execucao


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tf-dir', help='environment do terraform (lê os outputs)')
    parser.add_argument('--silver-database', help=AJUDA_SOBRESCREVE)
    parser.add_argument('--gold-database', help=AJUDA_SOBRESCREVE)
    parser.add_argument('--workgroup', help=AJUDA_SOBRESCREVE)
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='imprime o SQL renderizado sem tocar a AWS',
    )
    return parser.parse_args(argv)


def _resolver_alvos(
    args: argparse.Namespace, exigir_workgroup: bool = True
) -> tuple[str, str, str]:
    """Nomes de database e workgroup: do argumento ou dos outputs do terraform.

    O dry-run só renderiza o SQL, então não exige workgroup (nem credencial).
    """
    silver, gold, workgroup = args.silver_database, args.gold_database, args.workgroup
    falta_algo = not (silver and gold) or (exigir_workgroup and not workgroup)
    if falta_algo:
        if not args.tf_dir:
            raise SystemExit(
                'informe --tf-dir OU (--silver-database, --gold-database, --workgroup)'
            )
        saidas = _saidas_do_terraform(args.tf_dir)
        silver = silver or saidas['silver_datavault']['value']['database']
        gold = gold or saidas['gold']['value']['database']
        workgroup = workgroup or saidas['gold']['value']['workgroup']
    return silver, gold, workgroup or ''


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    arquivos = arquivos_de_ddl()
    if not arquivos:
        _dizer('nenhum .sql encontrado em src/{cold,hot}/athena_gold/')
        return 1

    silver, gold, workgroup = _resolver_alvos(args, exigir_workgroup=not args.dry_run)
    _dizer(f'gold={gold} silver={silver} workgroup={workgroup or "(dry-run)"}')

    try:
        athena = None if args.dry_run else boto3.client('athena')
        for arquivo in arquivos:
            sql = renderizar(arquivo.read_text(encoding='utf-8'), silver, gold)
            if args.dry_run:
                print(f'\n-- {arquivo.relative_to(ROOT)}\n{sql}')
                continue
            _executar(athena, sql, workgroup, arquivo.name)
        _dizer(f'{len(arquivos)} view(s) da gold aplicadas')
        return 0
    except subprocess.CalledProcessError as erro:
        _dizer(f'ERRO: terraform output falhou (exit {erro.returncode})')
        return erro.returncode or 1
    except (BotoCoreError, ClientError, RuntimeError, TimeoutError) as erro:
        _dizer(f'ERRO ao aplicar a gold: {erro}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
