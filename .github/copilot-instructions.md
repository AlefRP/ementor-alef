# GitHub Copilot Instructions — AWS Lakehouse Mentoria

## Contexto do Projeto

Este repositorio e uma base educacional para implementacao de um **data lakehouse na AWS**, dividido em:

- **Camada Fria** — pipeline batch com FastAPI (EC2) → Lambda → S3 raw → Glue/Iceberg → Athena gold.
- **Camada Quente** — pipeline de eventos com API (EC2) → SQS → Lambda → S3 raw → Glue microbatch/Iceberg → Athena gold.
- **Camada Consumer** — consumo via Athena.
- **Governanca** — AWS Lake Formation + CloudWatch.

## Convencoes de Codigo

### Python
- Versao minima: **3.11**
- Formatador: **blue** (perfil compativel com black, 88 chars)
- Ordenacao de imports: **isort** com `profile = "black"`
- Nunca adicionar comentarios ou docstrings em codigo que nao foi modificado
- Validar seguranca com **bandit** antes de qualquer commit

### Estrutura de Modulos
- Codigo de producao fica exclusivamente em `src/`
- Testes ficam em `tests/unit/`, `tests/integration/`, `tests/taac/`
- Marcar testes de integracao com `@pytest.mark.integration`
- Marcar testes TAAC com `@pytest.mark.taac`

### AWS / Cloud
- Credenciais AWS nunca devem aparecer no codigo — usar IAM roles ou variaveis de ambiente
- Recursos S3: sempre usar particoes por `year/month/day` no path
- Lambdas: handler assinatura padrao `handler(event, context)`
- Glue jobs: usar `GlueContext` + `DynamicFrame`; Iceberg via catalogo Lake Formation
- Sempre incluir tratamento de erros e logging estruturado nas Lambdas e Glue jobs

## Esteira CI/CD

- Workflows em `.github/workflows/`
- `ci.yml`: roda em todo PR e push para `main`/`master` — format check, lint, seguranca, testes
- `sonar.yml`: scan SonarCloud com cobertura de testes
- SonarCloud configurado em `sonar-project.properties`

## Comportamento Esperado do Copilot

- Ao sugerir codigo Python, respeitar blue (88 chars, aspas duplas)
- Ao criar funcoes AWS Lambda, sempre incluir logging e tratamento basico de excecoes
- Ao criar Glue jobs, incluir configuracao de Iceberg no GlueContext
- Ao criar testes, seguir padrao `test_<unidade>_<cenario>` e usar pytest
- Nao gerar secrets, credenciais ou tokens hardcoded
- Preferir `boto3` para interacao com servicos AWS
- Infraestrutura como codigo usa Terraform; manter em `infra/terraform/environments/dev/`
- Ao escrever SQL para Athena, sempre incluir particoes nos predicados `WHERE`

## Dependencias de Desenvolvimento

Gerenciadas em `pyproject.toml` na secao `[project.optional-dependencies] dev`:
- `blue`, `isort`, `pytest`, `pytest-cov`, `bandit`, `pip-audit`

Instalar com:
```bash
pip install -e .[dev]
```

## Comandos Uteis

```bash
make check-format   # blue + isort --check
make lint           # compilacao python
make security       # bandit + pip-audit
make test           # todos os testes
make test-unit      # apenas unitarios
make test-integration
make test-taac
```
