# Ambiente Terraform alvo (sobrescreva com: make tf-plan TF_ENV=prod)
TF_ENV ?= prod
TF_DIR := infra/terraform/environments/$(TF_ENV)

.PHONY: install-prod install-hooks format check-format lint \
        security security-deps security-secrets secrets-baseline \
        test test-unit test-integration test-taac test-cov \
        tf-fmt tf-fmt-check tf-validate tf-lint tf-security tf-plan \
        quality ci

# ---- Setup ----
install-prod:
	python -m pip install --upgrade pip
	pip install -e .[prod]

install-hooks:
	pre-commit install

# ---- Qualidade de código (Python) ----
format:
	blue src tests
	isort src tests

check-format:
	blue --check src tests
	isort --check-only src tests

lint: check-format
	python -m compileall src tests

# ---- Segurança ----
security:
	bandit -q -r src
	pip-audit

security-deps:
	safety check

security-secrets:
	detect-secrets scan --baseline .secrets.baseline

# Regenera o baseline do detect-secrets (rode após revisar novos achados).
secrets-baseline:
	detect-secrets scan > .secrets.baseline

# ---- Testes ----
test:
	pytest

test-unit:
	pytest tests/unit

test-integration:
	pytest -m integration tests/integration

test-taac:
	pytest -m taac tests/taac

test-cov:
	pytest --junitxml=junit.xml --cov=src --cov-report=xml --cov-report=html --cov-report=term-missing

# ---- Infraestrutura (Terraform) ----
tf-fmt:
	terraform -chdir=$(TF_DIR) fmt -recursive

tf-fmt-check:
	terraform -chdir=$(TF_DIR) fmt -check -recursive

tf-validate:
	terraform -chdir=$(TF_DIR) init -backend=false
	terraform -chdir=$(TF_DIR) validate

tf-lint:
	tflint --chdir=$(TF_DIR)

tf-security:
	checkov -d $(TF_DIR)

tf-plan:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) plan -no-color

# ---- Agregados ----
quality: check-format lint security test
ci: quality tf-fmt-check tf-validate
