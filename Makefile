# Ambiente Terraform alvo (sobrescreva com: make tf-plan TF_ENV=prod)
TF_ENV ?= prod
TF_DIR := infra/terraform/environments/$(TF_ENV)
TF_ROOT := infra/terraform
TF_BOOTSTRAP := infra/terraform/bootstrap
TF_PLAN_FILE ?= tfplan
CHECKOV_ARGS ?=
# Recurso alvo do tf-force-arm: os buckets das camadas (todas as instâncias).
TF_FORCE_TARGET ?= module.storage.aws_s3_bucket.layer
# Buckets do lakehouse (prefixo fixo do projeto + camadas).
TF_PREFIX := alef-rp-aws-lakehouse-$(TF_ENV)
TF_BUCKETS := $(TF_PREFIX)-raw $(TF_PREFIX)-silver $(TF_PREFIX)-artifacts
ARTIFACTS_BUCKET ?= $(TF_PREFIX)-artifacts

.PHONY: install-prod install-hooks format check-format lint \
        security security-deps security-secrets secrets-baseline \
        test test-unit test-integration test-taac test-cov api-bundle \
        api-bundle-upload event-producer-bundle db-seeder-bundle seed-db \
        release-plan release-apply \
        tf-bootstrap-plan tf-bootstrap-apply \
        tf-fmt tf-fmt-check tf-validate tf-lint tf-security \
        tf-init tf-plan tf-plan-out tf-ensure-bundle tf-apply tf-apply-plan tf-output \
        tf-empty-buckets tf-force-arm tf-destroy-precheck tf-destroy \
        quality ci

# ---- Setup ----
install-prod:
	python -m pip install --upgrade pip
	pip install -e .[prod]

install-hooks:
	pre-commit install

# ---- Qualidade de código (Python) ----
format:
	blue src simulation tests
	isort src simulation tests

check-format:
	blue --check src simulation tests
	isort --check-only src simulation tests

lint: check-format
	python -m compileall src simulation tests

# ---- Segurança ----
# CVEs ignorados no pip-audit — todos do black, que o blue 0.9.1 fixa como
# `black==22.1.0`: nenhum tem upgrade possível sem trocar de formatador. O
# black aqui é dev-only e roda só sobre o código do repo, com flags fixas
# (`blue src simulation tests`), o que põe os três fora do nosso alcance:
#   PYSEC-2024-48 (CVE-2024-21503) — ReDoS ao formatar docstring hostil.
#   PYSEC-2026-2120 (CVE-2026-31900) — RCE na GitHub Action do black com
#     `use_pyproject: true`; a esteira não usa essa action.
#   PYSEC-2026-2121 (CVE-2026-32274) — path traversal na escrita do cache
#     quando `--python-cell-magics` vem do atacante; nunca passamos essa flag.
# Listados por ID PYSEC (o que o pip-audit reporta); os GHSA são os aliases.
PIP_AUDIT_IGNORE := PYSEC-2024-48 \
                    PYSEC-2026-2120 GHSA-v53h-f6m7-xcgm \
                    PYSEC-2026-2121 GHSA-3936-cmfr-pm3m

# bandit só lê [tool.bandit] do pyproject com -c explícito.
security:
	pip-audit --skip-editable $(addprefix --ignore-vuln ,$(PIP_AUDIT_IGNORE))
	bandit -c pyproject.toml -r src simulation -f json

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

# ---- Simulação (alimenta SQS e RDS; fora da arquitetura) ----
# Empacota o producer de eventos. `terraform validate` não executa archive_file,
# então só `tf-plan`/`tf-apply` dependem destes alvos.
event-producer-bundle:
	python scripts/bundle/event_producer_bundle.py

# Pacote da Lambda de seed do RDS (simulation/ + psycopg + faker + .sql),
# fixado em linux aarch64/cp313 — o alvo do runtime da função.
db-seeder-bundle:
	python scripts/bundle/db_seeder_bundle.py

# Semeia o banco privado invocando a Lambda de seed (idempotente).
seed-db:
	aws lambda invoke --function-name $$(terraform -chdir=$(TF_DIR) output -raw db_seeder_function_name) --cli-read-timeout 700 build/seed-response.json
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

tf-plan: event-producer-bundle db-seeder-bundle
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) plan -no-color

# ---- Alvos da esteira (plan salvo como artefato + apply exato do plan) ----
# DESTROY=1 planeja a destruição; FORCE=1 mantém a config alinhada ao state —
# quem de fato libera esvaziar os buckets é o tf-force-arm, antes deste plan.
# init -reconfigure: o job pode ter rodado tf-validate (backend=false) antes.
tf-plan-out: event-producer-bundle db-seeder-bundle
	terraform -chdir=$(TF_DIR) init -reconfigure
	terraform -chdir=$(TF_DIR) plan -no-color $(if $(DESTROY),-destroy -var="validate_bundle=false") $(if $(FORCE),-var="force_destroy=true") -out=$(TF_PLAN_FILE)
	terraform -chdir=$(TF_DIR) show -no-color $(TF_PLAN_FILE) > $(TF_DIR)/plan.txt

# Aplica exatamente o plan salvo por tf-plan-out (sem confirmação — só esteira).
tf-apply-plan:
	terraform -chdir=$(TF_DIR) apply -no-color $(TF_PLAN_FILE)

# Precheck do bundle da API (o gate do apply da EC2 lê o objeto no S3): bundle
# ausente -> builda/publica; bucket ausente (bootstrap do zero) -> cria o
# storage primeiro (fase 1) e publica — o apply completo vira a fase 2. Sem
# isso, esses dois estados matavam o apply no meio, após ~12 min de retry do
# gate. Chamado pelo tf-apply manual E pelo rollback.yml da esteira, que passa
# AUTO_APPROVE=1 (fase 1 sem confirmação) e OVERWRITE=1 (republica o bundle do
# ref alvo: etag novo => user_data novo => EC2 substituída no apply).
tf-ensure-bundle:
	terraform -chdir=$(TF_DIR) init
	python scripts/deploy/ensure_api_bundle.py --tf-dir $(TF_DIR) --bucket $(ARTIFACTS_BUCKET) $(if $(AUTO_APPROVE),--auto-approve) $(if $(OVERWRITE),--overwrite)

# Apply manual do ambiente (o terraform pede confirmação; na esteira, apply
# existe só no rollback.yml, sempre a partir de um plan salvo).
tf-apply: event-producer-bundle db-seeder-bundle tf-ensure-bundle
	terraform -chdir=$(TF_DIR) apply

tf-output:
	terraform -chdir=$(TF_DIR) output

# Esvazia buckets versionados (raw, silver, artifacts) via API — deleta todas
# as versões e delete markers. Necessário antes do tf-destroy com FORCE=1,
# já que force_destroy do Terraform não remove versões de buckets versionados.
tf-empty-buckets:
	python scripts/teardown/empty_versioned_bucket.py $(TF_BUCKETS)

# O provider lê `force_destroy` do STATE na hora de deletar o bucket — passar
# -var no destroy não tem efeito. Este alvo grava o flag no state (update
# in-place, só nos buckets) para que o destroy seguinte possa esvaziá-los.
# AUTO_APPROVE=1 dispensa a confirmação (uso da esteira).
tf-force-arm: event-producer-bundle db-seeder-bundle tf-empty-buckets
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) apply -var="force_destroy=true" -target=$(TF_FORCE_TARGET) $(if $(AUTO_APPROVE),-auto-approve)

# Destroi TODA a infra do ambiente (terraform pede confirmação digitando "yes").
# Buckets com dados exigem FORCE=1 (arma force_destroy + esvazia raw/silver/artifacts
# via scripts/teardown/empty_versioned_bucket.py antes do destroy).
# O bucket de state (bootstrap) fica de pé por design (prevent_destroy).
# Sem FORCE, um destroy com dados nos buckets roda ~20 min e falha só no
# último recurso (BucketNotEmpty). Este precheck falha em segundos e aponta
# o comando certo. Bucket inexistente conta como vazio (teardown parcial).
tf-destroy-precheck:
	python scripts/teardown/empty_versioned_bucket.py --check $(TF_BUCKETS)

# validate_bundle=false: o refresh do destroy lê data sources; sem isso, um
# bundle ausente no bucket de artefatos travaria o teardown.
tf-destroy: $(if $(FORCE),tf-force-arm,tf-destroy-precheck)
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) destroy -var="validate_bundle=false" $(if $(FORCE),-var="force_destroy=true")

# ---- Agregados ----
quality: check-format lint security test
ci: quality tf-fmt-check tf-validate
