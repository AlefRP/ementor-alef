# Projeto Base - Arquitetura AWS Lakehouse (Mentoria)

Este repositorio contem a estrutura inicial para um projeto de lakehouse na AWS, com separacao entre camada fria, camada quente, camada de consumo, governanca e esteira de dados via GitHub Actions.

Objetivo: permitir que o mentorado implemente os componentes de negocio sobre uma base pronta de organizacao, qualidade e pipeline.

---

## Diagrama da Arquitetura

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                          CAMADA FRIA (batch)                            │
│                                                                         │
│  EC2 (FastAPI)  ──►  Lambda (EventBridge)  ──►  S3 raw                 │
│                                                    │                   │
│                              Glue Job (Iceberg) ◄──┘                   │
│                                    │                                   │
│                              S3 silver  ──►  Athena Views (gold)       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         CAMADA QUENTE (eventos)                         │
│                                                                         │
│  EC2 (Event API)  ──►  SQS  ──►  Lambda  ──►  S3 raw                  │
│                                                    │                   │
│                     Glue Microbatch (Iceberg) ◄────┘                   │
│                              │                                         │
│                        S3 silver  ──►  Athena Views (gold)             │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────┐   ┌──────────────────────────────┐
│        CAMADA CONSUMER           │   │       GOVERNANCA             │
│  Athena queries sobre gold       │   │  Lake Formation + CloudWatch │
└──────────────────────────────────┘   └──────────────────────────────┘
```

---

## Escopo da Arquitetura

### Camada Fria (batch)
1. API de data product em FastAPI (deploy em EC2) para expor dados.
2. Lambda agendada via EventBridge para consumir a API e salvar na raw (S3).
3. Job Glue (agendado via EventBridge) para ler raw e escrever silver em Iceberg.
4. Views no Athena para criar camada gold a partir da silver.

### Camada Quente (eventos)
1. Gerador de eventos (data product) em API (deploy em EC2).
2. API publica eventos no SQS.
3. Lambda acionada por SQS persiste dados na raw (S3).
4. Job Glue microbatch (agendado via EventBridge) transforma raw em silver (Iceberg).
5. Views no Athena disponibilizam camada gold.

### Camada Consumer
- Consumo analitico de dados via Athena.

### Camada Governanca
- AWS Lake Formation para controle de permissoes e governanca do lakehouse.
- CloudWatch para observabilidade e monitoramento de toda a arquitetura.

---

## Esteira de Dados (CI/CD)

Configurada com GitHub Actions e SonarCloud (gratuito para repositorios publicos).

### Gatilhos por evento

| Evento | Quality & Tests | Terraform Plan | SonarCloud |
|---|:---:|:---:|:---:|
| `push` em `feature/**` | ✅ | ✅ (apos quality) | ❌ |
| PR aberto → `main`/`master` | ✅ | ❌ | ✅ |
| `push` em `main`/`master` | ✅ | ❌ | ✅ |

### Gates de qualidade

| Gate | Ferramenta |
|---|---|
| Formatacao | blue + isort |
| Compilacao | python -m compileall |
| Seguranca | bandit + pip-audit |
| Testes | pytest (unit / integration / TAAC) |
| Infraestrutura | terraform validate + terraform plan |
| Qualidade de codigo | SonarCloud |

### Arquivos da esteira

- `.github/workflows/ci.yml` — lint, seguranca, testes (matrix Python 3.11/3.12/3.13) e terraform plan/checks contra a AWS
- `.github/workflows/sonar.yml` — cobertura + scan SonarCloud
- `.github/workflows/rollback.yml` — rollback manual do ambiente prod
- `.github/dependabot.yml` — atualizacao automatica de GitHub Actions, dependencias pip e modulos Terraform
- `.pre-commit-config.yaml` — hooks locais que espelham os gates (blue, isort, bandit, detect-secrets, terraform fmt)
- `sonar-project.properties` — configuracao do projeto no SonarCloud

O CI publica artefatos por execucao: relatorios de cobertura (XML + HTML), resultados JUnit por versao de Python, relatorios de seguranca em SARIF (aba Security > Code scanning) e o `terraform plan` (trilha de auditoria).

### Secrets necessarios no repositorio GitHub

| Secret | Usado em |
|---|---|
| `SONAR_TOKEN` | sonar.yml |
| `AWS_ACCESS_KEY_ID` | ci.yml (terraform-plan) |
| `AWS_SECRET_ACCESS_KEY` | ci.yml (terraform-plan) |
| `AWS_DEFAULT_REGION` | ci.yml (terraform-plan) |

---

## Estrutura de Pastas

A estrutura abaixo mostra os diretorios existentes (com `.gitkeep`) e os subdiretorios que devem ser criados durante a implementacao:

```text
.
|-- .github/
|   |-- copilot-instructions.md
|   |-- pull_request_template.md
|   `-- workflows/
|       |-- ci.yml
|       `-- sonar.yml
|-- infra/
|   `-- terraform/
|       `-- environments/
|           `-- prod/          ← IaC do ambiente de producao
|-- src/
|   |-- cold/                 ← camada fria
|   |   |-- api_fastapi/      ← a criar: FastAPI + Dockerfile
|   |   |-- lambda_ingest/    ← a criar: handler.py + requirements.txt
|   |   |-- glue_silver/      ← a criar: job.py + config
|   |   `-- athena_gold/      ← a criar: DDL de views .sql
|   |-- hot/                  ← camada quente
|   |   |-- event_generator_api/ ← a criar: API + Dockerfile
|   |   |-- lambda_raw_ingest/   ← a criar: handler.py
|   |   |-- glue_silver_microbatch/ ← a criar: job.py
|   |   `-- athena_gold/      ← a criar: DDL de views .sql
|   `-- consumer/             ← camada de consumo
|       `-- athena_queries/   ← a criar: queries analiticas .sql
|-- tests/
|   |-- unit/
|   |-- integration/
|   `-- taac/
|-- .gitignore
|-- Makefile
|-- pyproject.toml
`-- sonar-project.properties
```

---

## Como comecar

```bash
# 1. Criar e ativar ambiente virtual
python -m venv .venv && source .venv/bin/activate

# 2. Instalar dependencias de desenvolvimento
pip install -e .[prod]

# 3. Instalar os hooks de pre-commit (espelham os gates do CI)
make install-hooks

# 4. Validar qualidade antes de qualquer commit
make check-format
make lint
make security
make test
```

---

## Dicas de Implementacao por Componente

### API FastAPI (camada fria)
- Definir contrato de dados versionado (schema + paginacao).
- Incluir endpoint `/health` para o EventBridge/Lambda validar disponibilidade.
- Padronizar erros HTTP com `HTTPException` e correlation id nos logs.
- Dockerizar e criar script de deploy no EC2 (systemd ou supervisor).

### Lambda de ingestao batch
- Usar `boto3` para gravar no S3 com particoes por `year/month/day/hour`.
- Implementar idempotencia via checksum ou marker de ultima execucao.
- Registrar metricas customizadas no CloudWatch (volume, latencia, erros).

### Glue Silver com Iceberg
- Configurar `GlueContext` com catalogo Iceberg via Lake Formation.
- Definir estrategia de `MERGE INTO` para dados tardios.
- Agendar compactacao periodica (`OPTIMIZE` + `VACUUM`) para controle de custo.
- Versionamento de schema habilitado por padrao no Iceberg.

### Athena Gold
- Criar views semanticas orientadas ao dominio de negocio.
- Versionar DDL como arquivos `.sql` no repositorio.
- Particionar a consulta para evitar full scan e reduzir custo.

### Camada quente (SQS + Lambda)
- Incluir `messageGroupId` e chave idempotente no payload do evento.
- Configurar Dead Letter Queue (DLQ) para eventos invalidos.
- Ajustar `batchSize` e `visibilityTimeout` do SQS conforme throughput.

### Governanca
- Lake Formation: criar `data lake locations`, registrar databases e aplicar `LF-tags` por dominio.
- CloudWatch: alarmes para `Lambda Errors`, `Glue Job Failures` e `SQS ApproximateNumberOfMessagesNotVisible`.

---

## Dicas para o primeiro PR

- Implementar o caminho vertical minimo da camada fria:
  `API → Lambda batch → S3 raw → Glue Silver → Athena Gold`.
- PR pequeno e focado, com testes unitarios cobrindo o fluxo.
- Todos os checks da esteira devem estar verdes antes do merge.

---

## Configuracao do SonarCloud

O projeto usa **SonarCloud** (gratuito para repos publicos):

1. Acesse [sonarcloud.io](https://sonarcloud.io) e conecte com sua conta GitHub.
2. Importe o repositorio e copie o `projectKey` e `organization`.
3. Atualize `sonar-project.properties` com os valores corretos.
4. Adicione o secret `SONAR_TOKEN` nas configuracoes do repositorio GitHub.

> `SONAR_HOST_URL` nao e necessario — o workflow ja aponta para `https://sonarcloud.io`.

## Referencias para a Sprint 1
[Terraform - Provider AWS](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
[Introducao a Testes Unitarios](https://www.youtube.com/watch?v=pZvhZ-Lr-PE)
[Introducao a Testes com mock](https://www.youtube.com/watch?v=8uiMnwIkPYA)
[Pytest Fixtures](https://www.youtube.com/watch?v=sidi9Z_IkLU)
[Playlist Desenvolvimento de uma lib - Importante para aprender tecnicas de programacao profissional](https://www.youtube.com/watch?v=R3hCkU4EXgY)
[Curso FastAPI - Gratuito](https://www.youtube.com/watch?v=ImhYlISeWPQ&list=PLOQgLBuj2-3KT9ZWvPmaGFQ0KjIez0403)
[Curso FastAPI - Pago](https://www.udemy.com/course/fastapi-apis-modernas-e-assincronas-com-python/?referralCode=6E89EB8C04280DEA5983)
[Curso AWS - Essencial](https://www.udemy.com/course/amazon-web-services-essencial/?referralCode=835315E4467A40447001)
[Programacao Assincrona](https://www.udemy.com/course/programacao-concorrente-e-assincrona-com-python/?referralCode=CDFB0EDDE8648B7DDE15)
[Curso Design Patterns](https://www.udemy.com/course/padroes-de-projeto-com-python/?referralCode=0BC87A15DEC26B50505B)
[Design Patterns docs](https://refactoring.guru/design-patterns)
[Livro Computacao](https://www.amazon.com.br/Cientista-Computa%C3%A7%C3%A3o-Autodidata-Estruturas-Algoritmos/dp/8575228374/ref=sr_1_1?__mk_pt_BR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=21HYZK2Y40TWD&dib=eyJ2IjoiMSJ9.k-TIy9ot0B7FvP05Tc4SQHxMum3WXb7YClwTRyVdjLdYyTGU56pOTqp4D6AKHqTpybcc860XhceEnb9gjSYP3G-HZBTW_aENE3u78mZv4UkNBo7iv_JDTYRcLQM7ymxWt3EK7xPNMLNjkUpC0q94sk0l9L29gwMJEQX-Ms-WfMwHNvKvS80a3oilKmbu-0Gl.0p77zmiCSmrdfCuzAKvrYNGCUcq1FSRizMqQlPoKz6k&dib_tag=se&keywords=Cientista+da+Computa%C3%A7%C3%A3o+Autodidata&qid=1778100752&s=books&sprefix=cientista+da+computa%C3%A7%C3%A3o+autodidata%2Cstripbooks%2C217&sr=1-1)
[Curso esteira de Dados](https://cursos.alura.com.br/formacao-devops)
[Testes Integracao](https://www.youtube.com/watch?v=qq8b1bck9AU)
[Pipeline Terraform - Usar como referencia](https://www.youtube.com/watch?v=1TNAUW7_bC0)
[Curso Docker](https://www.udemy.com/course/docker-essencial-para-o-desenvolvedor/?referralCode=4180ED98E508AEAAE5FF)
[Shadow Traffic](https://shadowtraffic.io/)
[Curso de Claude Code - Recomendado](https://www.youtube.com/watch?v=MzMM5iV3GcU)

