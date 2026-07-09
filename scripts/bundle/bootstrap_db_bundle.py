#!/usr/bin/env python3
"""Empacota a Lambda de bootstrap do banco (schema + seed + api_reader).

A Lambda roda em **linux arm64 / python3.13** (ver modules/bootstrap_db), então
as deps nativas — psycopg[binary], que embute a libpq — precisam vir como wheels
manylinux aarch64. `pip install`/`pip wheel` resolveriam para o host, gerando um
zip que sobe mas falha no import; só `pip download --platform` faz alvo cruzado.

O zip contém o pacote `bootstrap_db/` (handler + os .sql, cuja fonte única é
scripts/database/) e o pacote `synthetic/` (simulação dos dados), por isso o
handler é `bootstrap_db.handler.handler`.

Multiplataforma de propósito: roda igual no Windows e no Ubuntu do CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build' / 'bootstrap-db'
PACKAGE_SRC = ROOT / 'src' / 'cold' / 'bootstrap_db'
SYNTHETIC_SRC = ROOT / 'synthetic'
SQL_SRC = ROOT / 'scripts' / 'database'

# Alvo do runtime da Lambda (ver modules/bootstrap_db/main.tf).
PYTHON_VERSION = '3.13'
ABI = 'cp313'
PLATFORMS = (
    'manylinux2014_aarch64',
    'manylinux_2_17_aarch64',
    'manylinux_2_28_aarch64',
)
SQL_FILES = ('olist_schema.sql', 'create_api_reader.sql')


def main() -> int:
    shutil.rmtree(BUILD, ignore_errors=True)
    package = BUILD / 'bootstrap_db'
    package.mkdir(parents=True, exist_ok=True)

    platform_flags: list[str] = []
    for platform in PLATFORMS:
        platform_flags += ['--platform', platform]

    # Deps no diretório raiz do zip (import top-level), com wheels do alvo.
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
            str(PACKAGE_SRC / 'requirements.txt'),
        ],
        check=True,
    )
    # pip download deixa .whl; a Lambda precisa dos módulos descompactados.
    for wheel in BUILD.glob('*.whl'):
        shutil.unpack_archive(str(wheel), str(BUILD), format='zip')
        wheel.unlink()

    for name in ('__init__.py', 'handler.py'):
        shutil.copy(PACKAGE_SRC / name, package / name)
    for name in SQL_FILES:
        shutil.copy(SQL_SRC / name, package / name)

    # O handler importa `synthetic.olist` (simulação das tabelas do Olist).
    shutil.copytree(
        SYNTHETIC_SRC,
        BUILD / 'synthetic',
        ignore=shutil.ignore_patterns('__pycache__'),
    )

    print(f'>> Bundle da bootstrap pronto em {BUILD} (linux aarch64/{ABI})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
