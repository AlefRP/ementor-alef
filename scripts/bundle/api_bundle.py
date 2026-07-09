#!/usr/bin/env python3
"""Empacota o bundle offline da API (camada fria) em build/api-bundle.tar.gz.

A EC2 da API é Amazon Linux 2023 **x86_64** com **python3.11**, e instala com
`pip install --no-index --find-links wheelhouse`. Duas consequências:

1. O alvo do artefato é fixo (linux x86_64 / cp311) — NÃO o host que builda.
   `pip wheel` compila para a plataforma local, então num Windows geraria
   wheels win_amd64 e o deploy quebraria. Usamos `pip download --platform`
   (que só existe no download) para as deps com código nativo — psycopg[binary]
   e pydantic-core.
2. O projeto em si é Python puro (py3-none-any), então vai de `pip wheel`.

Multiplataforma de propósito: chamado pelo alvo `api-bundle` do Makefile, roda
igual no Windows (PowerShell, make -> cmd.exe) e no Ubuntu do CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build' / 'api-bundle'
WHEELHOUSE = BUILD / 'wheelhouse'
TARBALL = ROOT / 'build' / 'api-bundle.tar.gz'

# Alvo do runtime da EC2 (ver modules/api_ec2: AMI al2023 x86_64 + python3.11).
PYTHON_VERSION = '3.11'
ABI = 'cp311'
# Várias tags manylinux: wheels novas podem exigir 2_28; antigas, 2_17/2014.
PLATFORMS = (
    'manylinux2014_x86_64',
    'manylinux_2_17_x86_64',
    'manylinux_2_28_x86_64',
)


def _api_dependencies() -> list[str]:
    """Lê [project.optional-dependencies].api — fonte única das deps da API."""
    with open(ROOT / 'pyproject.toml', 'rb') as handle:
        pyproject = tomllib.load(handle)
    return pyproject['project']['optional-dependencies']['api']


def _pip(*args: str) -> None:
    subprocess.run([sys.executable, '-m', 'pip', *args], check=True)


def main() -> int:
    shutil.rmtree(BUILD, ignore_errors=True)
    TARBALL.unlink(missing_ok=True)
    WHEELHOUSE.mkdir(parents=True, exist_ok=True)

    platform_flags: list[str] = []
    for platform in PLATFORMS:
        platform_flags += ['--platform', platform]

    # Deps de terceiros: wheels binárias já compiladas para o alvo da EC2.
    # --only-binary=:all: é exigido pelo pip sempre que se usa --platform.
    _pip(
        'download',
        '--dest',
        str(WHEELHOUSE),
        '--only-binary=:all:',
        '--implementation',
        'cp',
        '--python-version',
        PYTHON_VERSION,
        '--abi',
        ABI,
        *platform_flags,
        *_api_dependencies(),
    )

    # O projeto é Python puro: um único wheel py3-none-any serve em qualquer
    # plataforma. --no-deps porque as deps já vieram acima, no alvo correto.
    _pip('wheel', '--no-deps', '--wheel-dir', str(WHEELHOUSE), str(ROOT))

    with tarfile.open(TARBALL, 'w:gz') as tar:
        tar.add(WHEELHOUSE, arcname='wheelhouse')

    count = len(list(WHEELHOUSE.glob('*.whl')))
    print(f'>> Bundle da API pronto: {TARBALL} ({count} wheels, linux x86_64/{ABI})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
