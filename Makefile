# Ambiente Terraform alvo (sobrescreva com: make tf-plan TF_ENV=prod)
TF_ENV ?= prod
TF_DIR := infra/terraform/environments/$(TF_ENV)
TF_ROOT := infra/terraform
TF_BOOTSTRAP := infra/terraform/bootstrap
TF_PLAN_FILE ?= tfplan
CHECKOV_ARGS ?=

.PHONY: install-prod install-hooks format check-format lint \
        security security-deps security-secrets secrets-baseline \
        test test-unit test-integration test-taac test-cov \
        tf-bootstrap-plan tf-bootstrap-apply \
        tf-fmt tf-fmt-check tf-validate tf-lint tf-security \
        tf-init tf-plan tf-plan-out tf-apply tf-apply-plan tf-output tf-destroy \
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
	pip-audit --skip-editable
	bandit -r src -f json

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
# Bootstrap do state remoto: apply ÚNICO com state local (cria o bucket que os
# ambientes usam como backend). Rode antes do primeiro tf-init/tf-plan.
tf-bootstrap-plan:
	terraform -chdir=$(TF_BOOTSTRAP) init
	terraform -chdir=$(TF_BOOTSTRAP) plan

tf-bootstrap-apply:
	terraform -chdir=$(TF_BOOTSTRAP) init
	terraform -chdir=$(TF_BOOTSTRAP) apply

# fmt e checkov varrem a árvore inteira (modules/ + environments/ + bootstrap/).
tf-fmt:
	terraform -chdir=$(TF_ROOT) fmt -recursive

tf-fmt-check:
	terraform -chdir=$(TF_ROOT) fmt -check -recursive

tf-validate:
	terraform -chdir=$(TF_DIR) init -backend=false
	terraform -chdir=$(TF_DIR) validate

tf-lint:
	tflint --chdir=$(TF_DIR)

tf-security:
	checkov -d $(TF_ROOT) $(CHECKOV_ARGS)

tf-init:
	terraform -chdir=$(TF_DIR) init

tf-plan:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) plan -no-color

# ---- Alvos da esteira (plan salvo como artefato + apply exato do plan) ----
# DESTROY=1 planeja a destruição; FORCE=1 permite esvaziar buckets raw/silver.
# init -reconfigure: o job pode ter rodado tf-validate (backend=false) antes.
tf-plan-out:
	terraform -chdir=$(TF_DIR) init -reconfigure
	terraform -chdir=$(TF_DIR) plan -no-color $(if $(DESTROY),-destroy) $(if $(FORCE),-var="force_destroy=true") -out=$(TF_PLAN_FILE)
	terraform -chdir=$(TF_DIR) show -no-color $(TF_PLAN_FILE) > $(TF_DIR)/plan.txt

# Aplica exatamente o plan salvo por tf-plan-out (sem confirmação — só esteira).
tf-apply-plan:
	terraform -chdir=$(TF_DIR) apply -no-color $(TF_PLAN_FILE)

# Apply manual do ambiente (a esteira só faz plan; o terraform pede confirmação).
tf-apply:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) apply

tf-output:
	terraform -chdir=$(TF_DIR) output

# Destroi TODA a infra do ambiente (terraform pede confirmação digitando "yes").
# Buckets com dados exigem FORCE=1 (esvazia raw/silver antes de destruir).
# O bucket de state (bootstrap) fica de pé por design (prevent_destroy).
tf-destroy:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) destroy $(if $(FORCE),-var="force_destroy=true")

# ---- Agregados ----
quality: check-format lint security test
ci: quality tf-fmt-check tf-validate
