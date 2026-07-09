"""Testes da Lambda de bootstrap do banco (schema + seed + api_reader)."""
from pathlib import Path
from unittest import mock

import pytest

from src.cold.bootstrap_db import handler as bootstrap

SQL_SOURCE = Path(__file__).resolve().parents[3] / 'scripts' / 'database'


@pytest.fixture()
def bootstrap_env(monkeypatch):
    """Ambiente mínimo; os .sql moram em scripts/ (copiados no bundle)."""
    monkeypatch.setenv('PGHOST', 'db.interno')
    monkeypatch.setenv('PGPASSWORD', 'segredo-de-teste')  # nosec B105
    monkeypatch.setenv('SEED_ORDERS', '7')
    monkeypatch.setattr(bootstrap, 'SQL_DIR', SQL_SOURCE)


def _connection(order_count: int):
    """psycopg.connect(...) usado como context manager, com cursor mockado."""
    cursor = mock.MagicMock()
    cursor.fetchone.return_value = (order_count,)
    conn = mock.MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    connect = mock.MagicMock()
    connect.return_value.__enter__.return_value = conn
    return connect, conn, cursor


def test_config_reads_sizes_from_environment(bootstrap_env):
    config = bootstrap._config()
    assert config['host'] == 'db.interno'
    assert config['sizes']['orders'] == 7
    # Tabelas sem env var caem no default.
    assert config['sizes']['customers'] == bootstrap.olist.DEFAULT_SIZES['customers']


def test_config_requires_password(bootstrap_env, monkeypatch):
    monkeypatch.delenv('PGPASSWORD')
    with pytest.raises(KeyError):
        bootstrap._config()


def test_handler_seeds_when_database_is_empty(bootstrap_env):
    connect, conn, cursor = _connection(order_count=0)
    with mock.patch.object(bootstrap.psycopg, 'connect', connect):
        result = bootstrap.handler({}, None)

    assert result['statusCode'] == 200
    assert result['already_seeded'] is False
    assert result['rows']['orders'] == 7
    # Schema e create_api_reader executados; COPY chamado por tabela.
    assert cursor.copy.call_count == len(bootstrap.olist.COLUMNS)
    assert conn.commit.call_count >= 3


def test_handler_is_idempotent_when_already_seeded(bootstrap_env):
    connect, _, cursor = _connection(order_count=500)
    with mock.patch.object(bootstrap.psycopg, 'connect', connect):
        result = bootstrap.handler({}, None)

    assert result['already_seeded'] is True
    assert result['rows'] == {}
    cursor.copy.assert_not_called()  # nada é recarregado


def test_handler_runs_schema_before_api_reader(bootstrap_env):
    connect, _, cursor = _connection(order_count=0)
    with mock.patch.object(bootstrap.psycopg, 'connect', connect):
        bootstrap.handler({}, None)

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    schema_at = next(i for i, sql in enumerate(executed) if 'CREATE SCHEMA' in sql)
    reader_at = next(i for i, sql in enumerate(executed) if 'api_reader' in sql)
    assert schema_at < reader_at


def test_handler_propagates_connection_failure(bootstrap_env):
    with mock.patch.object(
        bootstrap.psycopg, 'connect', side_effect=RuntimeError('sem rota')
    ):
        with pytest.raises(RuntimeError):
            bootstrap.handler({}, None)
