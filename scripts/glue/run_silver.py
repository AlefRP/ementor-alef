#!/usr/bin/env python3
"""Dispara os jobs Glue da camada silver e espera cada um concluir.

As views da gold (``src/{cold,hot}/athena_gold/*.sql``) leem as tabelas Data
Vault da silver. No merge à master a esteira aplica a gold logo após o apply,
mas essas tabelas só passam a existir depois que o job Glue silver roda — e fora
daqui ele é AGENDADO por EventBridge Scheduler, não roda no apply. Num ambiente
recém-aplicado a silver ainda não materializou nada e o ``CREATE OR REPLACE
VIEW`` quebra em ``Table '...silver_datavault.sat_customer_profile' does not
exist``. Este script roda a silver (fria e quente) e espera o ``SUCCEEDED``
ANTES do ``make athena-gold``, garantindo o contrato de tabelas que a gold lê.

``StartJobRun`` é assíncrono: dispara e devolve um ``JobRunId``; aqui esperamos o
estado terminal de cada run. Os dois jobs são independentes, então disparamos os
dois e só então esperamos — rodam em paralelo. Reprocessar a silver é seguro: os
merges do Data Vault são insert-only por hash key (hubs/links) e append por
hashdiff (satélites).

Os jobs têm ``max_concurrent_runs = 1``: se a agenda já disparou um run, o
StartJobRun devolve ``ConcurrentRunsExceededException`` — nesse caso esperamos a
execução em andamento em vez de falhar.

Uso:
    python scripts/glue/run_silver.py --tf-dir infra/terraform/environments/prod
    python scripts/glue/run_silver.py --jobs meu-job-cold meu-job-hot
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# STARTING/RUNNING/STOPPING não são terminais; o resto encerra o run.
ESTADOS_TERMINAIS = {'SUCCEEDED', 'FAILED', 'TIMEOUT', 'STOPPED', 'ERROR'}
INTERVALO_DE_POLLING = 15
# Acima do timeout do próprio job (60 min no cold): se o Glue estourar, o run vai
# para TIMEOUT e tratamos como falha; esta trava é só a rede de segurança.
TIMEOUT_SEGUNDOS = 75 * 60

AJUDA_SOBRESCREVE = 'sobrescreve o output do terraform'


def _dizer(mensagem: str) -> None:
    print(f'>> {mensagem}', flush=True)


def _codigo_do_erro(erro: ClientError) -> str:
    return erro.response.get('Error', {}).get('Code', '')


def _saidas_do_terraform(tf_dir: str) -> dict:
    """Lê os outputs do environment (fonte única dos nomes dos jobs)."""
    resultado = subprocess.run(
        ['terraform', f'-chdir={tf_dir}', 'output', '-json'],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(resultado.stdout)


def _jobs_alvo(args: argparse.Namespace) -> list[str]:
    """Nomes dos jobs Glue: do argumento OU dos outputs do terraform."""
    if args.jobs:
        return args.jobs
    if not args.tf_dir:
        raise SystemExit('informe --tf-dir OU --jobs <cold> <hot>')
    silver = _saidas_do_terraform(args.tf_dir)['silver_datavault']['value']
    return [silver['cold_job'], silver['hot_job']]


def _run_em_andamento(glue, job_name: str) -> str | None:
    """Id do run não terminal mais recente do job, se houver (ordem: recente primeiro)."""
    for run in glue.get_job_runs(JobName=job_name, MaxResults=10).get('JobRuns', []):
        if run['JobRunState'] not in ESTADOS_TERMINAIS:
            return run['Id']
    return None


def _disparar(glue, job_name: str) -> str:
    """Dispara o job e devolve o id do run; reusa o run da agenda se já rodando."""
    try:
        run_id = glue.start_job_run(JobName=job_name)['JobRunId']
        _dizer(f'{job_name}: disparado (run {run_id})')
        return run_id
    except ClientError as erro:
        if _codigo_do_erro(erro) != 'ConcurrentRunsExceededException':
            raise
        existente = _run_em_andamento(glue, job_name)
        if not existente:
            raise
        _dizer(
            f'{job_name}: ja havia execucao em andamento (run {existente}) - aguardando-a'
        )
        return existente


def _esperar(glue, job_name: str, run_id: str) -> None:
    """Espera o run chegar a estado terminal; erro (ou não-SUCCEEDED) vira exceção."""
    limite = time.monotonic() + TIMEOUT_SEGUNDOS
    while True:
        detalhe = glue.get_job_run(JobName=job_name, RunId=run_id)['JobRun']
        estado = detalhe['JobRunState']
        if estado in ESTADOS_TERMINAIS:
            break
        if time.monotonic() > limite:
            raise TimeoutError(
                f'{job_name}: {TIMEOUT_SEGUNDOS // 60}min sem concluir ({estado})'
            )
        time.sleep(INTERVALO_DE_POLLING)

    if estado != 'SUCCEEDED':
        motivo = detalhe.get('ErrorMessage', 'sem detalhe')
        raise RuntimeError(f'{job_name}: {estado} - {motivo}')
    _dizer(f'{job_name}: OK')


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tf-dir', help='environment do terraform (lê os outputs)')
    parser.add_argument('--jobs', nargs='+', metavar='JOB', help=AJUDA_SOBRESCREVE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    jobs = _jobs_alvo(args)
    _dizer(f'silver: disparando {len(jobs)} job(s) e aguardando conclusao')

    try:
        glue = boto3.client('glue')
        # Dispara todos primeiro (rodam em paralelo), depois espera cada um.
        execucoes = [(nome, _disparar(glue, nome)) for nome in jobs]
        for nome, run_id in execucoes:
            _esperar(glue, nome, run_id)
        _dizer(f'{len(jobs)} job(s) da silver concluidos - gold pode ser aplicada')
        return 0
    except subprocess.CalledProcessError as erro:
        _dizer(f'ERRO: terraform output falhou (exit {erro.returncode})')
        return erro.returncode or 1
    except (BotoCoreError, ClientError, RuntimeError, TimeoutError) as erro:
        _dizer(f'ERRO ao rodar a silver: {erro}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
