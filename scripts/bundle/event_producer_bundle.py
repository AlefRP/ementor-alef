#!/usr/bin/env python3
"""Empacota a Lambda de SIMULAÇÃO que publica eventos no SQS.

Não faz parte da arquitetura do lakehouse — ela apenas alimenta a fila. Do SQS
para a frente é que começa a camada quente (``src/hot/lambda_raw_ingest``).

O zip embarca o pacote ``simulation/`` (handler + geradores Faker), por isso o
handler é ``simulation.event_producer.handler.handler``. O Faker é Python puro,
então basta ``pip install -t`` (sem necessidade de alvo cruzado).

Multiplataforma de propósito: roda igual no Windows e no Ubuntu do CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / 'build' / 'event-producer'
SIMULATION = ROOT / 'simulation'
REQUIREMENTS = SIMULATION / 'event_producer' / 'requirements.txt'

# O outro Lambda de simulação não precisa ir junto neste zip.
IGNORE = shutil.ignore_patterns('__pycache__', 'db_seeder')


def main() -> int:
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            '-m',
            'pip',
            'install',
            '--no-compile',
            '-r',
            str(REQUIREMENTS),
            '-t',
            str(BUILD_DIR),
        ],
        check=True,
    )
    shutil.copytree(SIMULATION, BUILD_DIR / 'simulation', ignore=IGNORE)
    print(f'>> Bundle do producer (simulacao) pronto em {BUILD_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
