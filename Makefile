# Ambiente Terraform alvo (sobrescreva com: make tf-plan TF_ENV=prod)
TF_ENV ?= prod
TF_DIR := infra/terraform/environments/$(TF_ENV)
TF_ROOT := infra/terraform
TF_BOOTSTRAP := infra/terraform/bootstrap
TF_PLAN_FILE ?= tfplan
CHECKOV_ARGS ?=

.PHONY: install-prod install-hooks format check-format lint \
        security security-deps security-secrets secrets-baseline \
        test test-unit test-integration test-taac test-cov api-bundle \
        api-bundle-upload hot-producer-bundle bootstrap-db-bundle seed-db \
        release-plan release-apply \
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
	blue src synthetic tests
	isort src synthetic tests

check-format:
	blue --check src synthetic tests
	isort --check-only src synthetic tests

lint: check-format
	python -m compileall src synthetic tests

# ---- Segurança ----
# Ignora CVEs do black 22.1.0 (ReDoS): pin transitivo do blue 0.9.1, sem fix
# disponível sem trocar de formatador; dev-only, só formata código do repo.
security:
	pip-audit --skip-editable --ignore-vuln PYSEC-2024-48 --ignore-vuln GHSA-3936-cmfr-pm3m
	bandit -r src synthetic -f json

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

# Gate local de cobertura (>= 90%) — espelhe o mesmo threshold no Quality
# Gate do SonarCloud (Administration > Quality Gates).
test-cov:
	pytest --junitxml=junit.xml --cov=src --cov-report=xml --cov-report=html --cov-report=term-missing --cov-fail-under=90

# ---- Deploy da API (bundle offline para a EC2 privada) ----
# Gera build/api-bundle.tar.gz com wheelhouse/ (projeto + extras [api]).
# A esteira sobe para s3://<prefix>-artifacts/api/ e o user_data da EC2
# instala com pip --no-index (rede 100% privada, via S3 gateway endpoint).
# Script Python (não shell) por dois motivos: roda igual no Windows e no CI, e
# fixa o alvo linux x86_64/cp311 da EC2 — `pip wheel` compilaria para o host,
# gerando wheels win_amd64 indeployáveis. Ver scripts/bundle/api_bundle.py.
api-bundle:
	python scripts/bundle/api_bundle.py

# Sobe o bundle para o bucket de artefatos (o user_data da EC2 lê daqui).
# Use após `make api-bundle` para um deploy local completo.
api-bundle-upload: api-bundle
	aws s3 cp build/api-bundle.tar.gz s3://$(ARTIFACTS_BUCKET)/api/api-bundle.tar.gz

# Empacota o producer da camada quente (Faker + handler) no diretório que o
# módulo hot_ingestion zipa (archive_file source_dir). `terraform validate` não
# executa archive_file, então só `tf-plan`/`tf-apply` dependem deste alvo.
# Script Python (não shell) para rodar igual no Windows e no Ubuntu do CI.
hot-producer-bundle:
	python scripts/bundle/hot_producer_bundle.py

# Pacote da Lambda de bootstrap do banco (handler + psycopg + faker + .sql),
# fixado em linux aarch64/cp313 — o alvo do runtime da função.
bootstrap-db-bundle:
	python scripts/bundle/bootstrap_db_bundle.py

# Semeia o banco privado invocando a Lambda de bootstrap (idempotente).
seed-db:
	aws lambda invoke --function-name $$(terraform -chdir=$(TF_DIR) output -raw bootstrap_db_function_name) --cli-read-timeout 700 build/seed-response.json
	python -c "import json;print(json.load(open('build/seed-response.json')))"

# ---- Release (CD) ----
# Fonte unica da versao: pyproject.toml ([project].version). Calcula a
# proxima versao semver a partir de Conventional Commits desde a ultima tag
# vX.Y.Z (grava outputs em $GITHUB_OUTPUT no CI; imprime no stdout em
# dry-run local). Ver scripts/release/release.py para o racional completo.
release-plan:
	python scripts/release/release.py plan

# Aplica o bump decidido pelo release-plan: version = "..." em
# pyproject.toml + entrada nova em CHANGELOG.md. VERSION e obrigatorio, ex.:
# make release-apply VERSION=1.2.0
release-apply:
	python scripts/release/release.py apply --version $(VERSION)

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

tf-plan: hot-producer-bundle bootstrap-db-bundle
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) plan -no-color

# ---- Alvos da esteira (plan salvo como artefato + apply exato do plan) ----
# DESTROY=1 planeja a destruição; FORCE=1 permite esvaziar buckets raw/silver.
# init -reconfigure: o job pode ter rodado tf-validate (backend=false) antes.
tf-plan-out: hot-producer-bundle bootstrap-db-bundle
	terraform -chdir=$(TF_DIR) init -reconfigure
	terraform -chdir=$(TF_DIR) plan -no-color $(if $(DESTROY),-destroy) $(if $(FORCE),-var="force_destroy=true") -out=$(TF_PLAN_FILE)
	terraform -chdir=$(TF_DIR) show -no-color $(TF_PLAN_FILE) > $(TF_DIR)/plan.txt

# Aplica exatamente o plan salvo por tf-plan-out (sem confirmação — só esteira).
tf-apply-plan:
	terraform -chdir=$(TF_DIR) apply -no-color $(TF_PLAN_FILE)

# Apply manual do ambiente (a esteira só faz plan; o terraform pede confirmação).
tf-apply: hot-producer-bundle bootstrap-db-bundle
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
