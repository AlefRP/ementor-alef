#!/usr/bin/env python3
"""Empacota o producer da camada quente (handler + Faker) no diretório que o
módulo Terraform hot_ingestion zipa (archive_file source_dir).

Multiplataforma de propósito: chamado pelo alvo `hot-producer-bundle` do
Makefile, que roda tanto no Windows (PowerShell, make -> cmd.exe) quanto no
Ubuntu do CI. Por isso usa shutil/subprocess em vez de rm/mkdir/cp.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / 'build' / 'hot-producer'
PRODUCER = ROOT / 'src' / 'hot' / 'event_producer'
SYNTHETIC = ROOT / 'synthetic'


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
            str(PRODUCER / 'requirements.txt'),
            '-t',
            str(BUILD_DIR),
        ],
        check=True,
    )
    shutil.copy(PRODUCER / 'handler.py', BUILD_DIR / 'handler.py')
    # O handler importa `synthetic.events` (simulação dos eventos).
    shutil.copytree(
        SYNTHETIC,
        BUILD_DIR / 'synthetic',
        ignore=shutil.ignore_patterns('__pycache__'),
    )
    print(f'>> Bundle do producer pronto em {BUILD_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
