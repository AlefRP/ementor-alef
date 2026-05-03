.PHONY: install-dev format check-format lint security test test-unit test-integration test-taac

install-dev:
	python -m pip install --upgrade pip
	pip install -e .[dev]

format:
	blue src tests
	isort src tests

check-format:
	blue --check src tests
	isort --check-only src tests

lint: check-format
	python -m compileall src tests

security:
	bandit -q -r src
	pip-audit

test:
	pytest

test-unit:
	pytest tests/unit

test-integration:
	pytest -m integration tests/integration

test-taac:
	pytest -m taac tests/taac
