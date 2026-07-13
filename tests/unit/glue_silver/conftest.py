"""Fixtures dos testes do runtime Glue silver (imports flat + Spark local).

O runtime é importado de forma flat (``from vault import ...``) porque no Glue
ele chega via ``--extra-py-files``; aqui reproduzimos isso pondo o diretório
no ``sys.path``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RUNTIME_DIR = Path(__file__).resolve().parents[3] / 'src' / 'glue_silver_runtime'
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

# Sem isto o Spark sobe o worker com o python do sistema, que pode divergir
# do interpretador dos testes (driver) e derrubar a conexão driver<->worker.
os.environ.setdefault('PYSPARK_PYTHON', sys.executable)
os.environ.setdefault('PYSPARK_DRIVER_PYTHON', sys.executable)


@pytest.fixture(scope='session')
def spark():
    """SparkSession local mínima para exercitar os builders do Data Vault."""
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master('local[2]')
        .appName('glue-silver-tests')
        .config('spark.sql.shuffle.partitions', '2')
        .config('spark.ui.enabled', 'false')
        .getOrCreate()
    )
    yield session
    session.stop()
