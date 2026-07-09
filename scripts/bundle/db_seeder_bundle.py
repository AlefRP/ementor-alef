#!/usr/bin/env python3
"""Empacota a Lambda de SIMULAÇÃO que semeia o RDS (schema + dados + api_reader).

Não faz parte da arquitetura do lakehouse — ela apenas prepara e alimenta o
banco de origem. Do RDS para a frente é que começa a camada fria (API de data
product -> ``src/cold/lambda_ingest``).

A Lambda roda em **linux arm64 / python3.13**, então as deps nativas —
psycopg[binary], que embute a libpq — precisam vir como wheels manylinux
aarch64. `pip install`/`pip wheel` resolveriam para o host, gerando um zip que
sobe mas falha no import; só `pip download --platform` faz alvo cruzado.

O zip embarca o pacote ``simulation/`` (handler + geradores + os .sql, cuja
fonte única é scripts/database/), por isso o handler é
``simulation.db_seeder.handler.handler``.

Multiplataforma de propósito: roda igual no Windows e no Ubuntu do CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build' / 'db-seeder'
SIMULATION = ROOT / 'simulation'
SQL_SRC = ROOT / 'scripts' / 'database'
REQUIREMENTS = SIMULATION / 'db_seeder' / 'requirements.txt'

# Alvo do runtime da Lambda (ver modules/simulation/db_seeder/main.tf).
PYTHON_VERSION = '3.13'
ABI = 'cp313'
PLATFORMS = (
    'manylinux2014_aarch64',
    'manylinux_2_17_aarch64',
    'manylinux_2_28_aarch64',
)
SQL_FILES = ('olist_schema.sql', 'create_api_reader.sql')

# O outro Lambda de simulação não precisa ir junto neste zip.
IGNORE = shutil.ignore_patterns('__pycache__', 'event_producer')


def main() -> int:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)

    platform_flags: list[str] = []
    for platform in PLATFORMS:
        platform_flags += ['--platform', platform]

    subprocess.run(
        [
            sys.executable,
            '-m',
            'pip',
            'download',
            '--dest',
            str(BUILD),
            '--only-binary=:all:',
            '--implementation',
            'cp',
            '--python-version',
            PYTHON_VERSION,
            '--abi',
            ABI,
            *platform_flags,
            '-r',
            str(REQUIREMENTS),
        ],
        check=True,
    )
    # pip download deixa .whl; a Lambda precisa dos módulos descompactados.
    for wheel in BUILD.glob('*.whl'):
        shutil.unpack_archive(str(wheel), str(BUILD), format='zip')
        wheel.unlink()

    shutil.copytree(SIMULATION, BUILD / 'simulation', ignore=IGNORE)
    for name in SQL_FILES:
        shutil.copy(SQL_SRC / name, BUILD / 'simulation' / 'db_seeder' / name)

    print(f'>> Bundle do seeder (simulacao) pronto em {BUILD} (linux aarch64/{ABI})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
