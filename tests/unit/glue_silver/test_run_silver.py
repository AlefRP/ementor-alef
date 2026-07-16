"""Testes do disparo e espera dos jobs Glue da silver (scripts/glue/run_silver.py).

Não tocam a AWS: um Glue falso exercita o disparo, a espera até o estado
terminal e o reuso da execução já em andamento (max_concurrent_runs = 1).
Todos seguem o padrão AAA: Arrange (preparar), Act (executar), Assert (verificar).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / 'scripts' / 'glue'))

import run_silver  # noqa: E402


class GlueFalso:
    """Glue mínimo: estados por job (consumidos em ordem) e erro de disparo."""

    def __init__(self, estados=None, erro_ao_disparar=None, runs_por_job=None):
        self._estados = {nome: list(seq) for nome, seq in (estados or {}).items()}
        self._erro_ao_disparar = erro_ao_disparar or {}
        self._runs_por_job = runs_por_job or {}
        self.disparados = []

    def start_job_run(self, JobName):
        erro = self._erro_ao_disparar.get(JobName)
        if erro is not None:
            raise erro
        self.disparados.append(JobName)
        return {'JobRunId': f'run-{JobName}'}

    def get_job_runs(self, JobName, MaxResults=10):
        return {'JobRuns': self._runs_por_job.get(JobName, [])}

    def get_job_run(self, JobName, RunId):
        estados = self._estados.get(JobName) or ['SUCCEEDED']
        estado = estados.pop(0) if len(estados) > 1 else estados[0]
        detalhe = {'Id': RunId, 'JobRunState': estado}
        if estado != 'SUCCEEDED':
            detalhe['ErrorMessage'] = 'boom'
        return {'JobRun': detalhe}


def _erro_concorrente() -> ClientError:
    return ClientError(
        {'Error': {'Code': 'ConcurrentRunsExceededException', 'Message': 'x'}},
        'StartJobRun',
    )


@pytest.fixture(autouse=True)
def _sem_sleep(monkeypatch):
    """Neutraliza o polling para os testes não esperarem de verdade."""
    monkeypatch.setattr(run_silver.time, 'sleep', lambda _segundos: None)


def test_jobs_alvo_usa_a_lista_explicita():
    # Arrange
    args = run_silver._interpretar_args(['--jobs', 'cold', 'hot'])

    # Act
    jobs = run_silver._jobs_alvo(args)

    # Assert
    assert jobs == ['cold', 'hot']


def test_jobs_alvo_le_dos_outputs_do_terraform(monkeypatch):
    # Arrange
    saidas = {
        'silver_datavault': {'value': {'cold_job': 'job-cold', 'hot_job': 'job-hot'}}
    }
    monkeypatch.setattr(run_silver, '_saidas_do_terraform', lambda _dir: saidas)
    args = run_silver._interpretar_args(['--tf-dir', 'infra/qualquer'])

    # Act
    jobs = run_silver._jobs_alvo(args)

    # Assert
    assert jobs == ['job-cold', 'job-hot']


def test_jobs_alvo_sem_fonte_falha():
    # Arrange
    args = run_silver._interpretar_args([])

    # Act / Assert — sem --jobs nem --tf-dir não há de onde tirar os nomes.
    with pytest.raises(SystemExit):
        run_silver._jobs_alvo(args)


def test_disparar_devolve_o_run_id():
    # Arrange
    glue = GlueFalso()

    # Act
    run_id = run_silver._disparar(glue, 'cold')

    # Assert
    assert run_id == 'run-cold'
    assert glue.disparados == ['cold']


def test_disparar_reusa_execucao_concorrente():
    # Arrange — a agenda já disparou; o StartJobRun bate no limite de 1 run.
    glue = GlueFalso(
        erro_ao_disparar={'cold': _erro_concorrente()},
        runs_por_job={'cold': [{'Id': 'run-agenda', 'JobRunState': 'RUNNING'}]},
    )

    # Act
    run_id = run_silver._disparar(glue, 'cold')

    # Assert
    assert run_id == 'run-agenda'


def test_disparar_propaga_erro_sem_run_ativo():
    # Arrange — concorrência sem execução ativa visível não é recuperável.
    glue = GlueFalso(erro_ao_disparar={'cold': _erro_concorrente()})

    # Act / Assert
    with pytest.raises(ClientError):
        run_silver._disparar(glue, 'cold')


def test_esperar_aceita_sucesso_apos_running():
    # Arrange
    glue = GlueFalso(estados={'cold': ['RUNNING', 'SUCCEEDED']})

    # Act / Assert — não levanta ao terminar em SUCCEEDED.
    run_silver._esperar(glue, 'cold', 'run-cold')


def test_esperar_falha_vira_excecao():
    # Arrange
    glue = GlueFalso(estados={'cold': ['FAILED']})

    # Act / Assert
    with pytest.raises(RuntimeError):
        run_silver._esperar(glue, 'cold', 'run-cold')


def test_main_dispara_todos_e_conclui(monkeypatch):
    # Arrange
    glue = GlueFalso(estados={'cold': ['SUCCEEDED'], 'hot': ['SUCCEEDED']})
    monkeypatch.setattr(run_silver.boto3, 'client', lambda _servico: glue)

    # Act
    codigo = run_silver.main(['--jobs', 'cold', 'hot'])

    # Assert
    assert codigo == 0
    assert glue.disparados == ['cold', 'hot']


def test_main_retorna_erro_quando_job_falha(monkeypatch):
    # Arrange
    glue = GlueFalso(estados={'cold': ['FAILED']})
    monkeypatch.setattr(run_silver.boto3, 'client', lambda _servico: glue)

    # Act
    codigo = run_silver.main(['--jobs', 'cold'])

    # Assert
    assert codigo == 1
