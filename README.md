# ☁️ Projeto Base — Arquitetura AWS Lakehouse (Mentoria)

[![CI](https://github.com/AlefRP/ementor-alef/actions/workflows/ci.yml/badge.svg)](https://github.com/AlefRP/ementor-alef/actions/workflows/ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=aws_ementor-alef&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=aws_ementor-alef)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=aws_ementor-alef&metric=coverage)](https://sonarcloud.io/summary/new_code?id=aws_ementor-alef)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)
![Terraform](https://img.shields.io/badge/terraform-%E2%89%A5%201.15.6-844FBA?logo=terraform&logoColor=white)

Este repositório contém a estrutura inicial para um projeto de lakehouse na AWS, com separação entre camada fria, camada quente, camada de consumo, governança e esteira de dados via GitHub Actions.

**Objetivo:** permitir que o mentorado implemente os componentes de negócio sobre uma base pronta de organização, qualidade e pipeline.

---

## 🗺️ Diagrama da Arquitetura

![Diagrama da arquitetura AWS Lakehouse](docs/img/arquitetura.png)

---

## 📚 Documentação

Este README é o ponto de entrada; o funcionamento do projeto está documentado em [`docs/`](docs/):

| Documento | O que responde |
| --- | --- |
| [Arquitetura](docs/arquitetura.md) | Como o lakehouse funciona de ponta a ponta: fronteiras, camadas fria/quente passo a passo, silver Data Vault/Iceberg, gold e governança |
| [Esteira CI/CD](docs/esteira.md) | Como o código chega em produção: gatilhos, jobs, workflows de CD/rollback/destroy, artefatos e secrets |
| [Operação](docs/operacao.md) | Runbook: subir o ambiente do zero, dia a dia, diagnóstico, rollback e teardown |
| [Padrão de testes](docs/padrao-de-testes.md) | Estrutura AAA, nomenclatura e exemplos executáveis em [`docs/exemplos/`](docs/exemplos/) |
| [Padrão de API](docs/padrao-de-api.md) | O padrão FastAPI de referência e como as APIs do repo o aplicam |
| [.claude/README.md](.claude/README.md) | Skills, agents, commands e lições que apoiam o desenvolvimento |

---

## 🎯 Escopo da Arquitetura

> O passo a passo de cada camada, a modelagem da silver e o mapa código ↔ infra
> estão em [docs/arquitetura.md](docs/arquitetura.md).

### ❄️ Camada Fria (batch)

1. API de data product em FastAPI (deploy em EC2) para expor dados.
2. Lambda agendada via EventBridge para consumir a API e salvar na raw (S3).
3. Job Glue (agendado via EventBridge) para ler a raw e escrever a silver em Iceberg.
4. Views no Athena para criar a camada gold a partir da silver.

### 🔥 Camada Quente (eventos)

1. **Event API** em FastAPI (deploy em EC2): recebe eventos, valida o contrato e publica no SQS.
2. Lambda acionada pelo SQS persiste os dados na raw (S3), com DLQ e reprocessamento por mensagem.
3. Job Glue microbatch (agendado via EventBridge) transforma raw em silver (Iceberg).
4. Views no Athena disponibilizam a camada gold.

> A EC2 é privada e não há NAT: como o SQS **não tem gateway endpoint gratuito**, a Event API alcança a fila por um **interface endpoint** (~US$ 0,01/h) — mesmo padrão já usado pelos endpoints do SSM. A alternativa gratuita seria expor a EC2 numa subnet pública, o que furaria a postura privada do resto da arquitetura.

### 📊 Camada Consumer

- Consumo analítico via Athena sobre a gold: queries versionadas em [`src/consumer/`](src/consumer/) (`make athena-query QUERY=<nome>`).

### 🥇 Camada Gold (as duas camadas)

A gold **não copia dados**: são views do Athena sobre a silver (Iceberg/Data Vault), devolvendo o modelo dimensional (`dim_`/`fact_`) que o negócio entende. O DDL é código versionado em [`src/cold/athena_gold/`](src/cold/athena_gold/) e [`src/hot/athena_gold/`](src/hot/athena_gold/); o Terraform cria só a infra (database + workgroup), e `make athena-gold` aplica as views (`CREATE OR REPLACE VIEW`, idempotente). A esteira roda isso no merge, logo após o apply.

### 🛡️ Camada de Governança

- AWS Lake Formation para controle de permissões e governança do lakehouse.
- CloudWatch para observabilidade: log group em todo componente **e alarmes** — erro nas Lambdas de ingestão, mensagem na DLQ, backlog envelhecendo na fila e status check das EC2 privadas (que não têm SSH: o alarme é o único aviso). Falha de job Glue tem caminho próprio (EventBridge → SNS).

---

## 🚀 Esteira de Dados (CI/CD)

Configurada com GitHub Actions e SonarCloud (gratuito para repositórios públicos), no padrão **merge-before-apply**: o `terraform plan` é revisado no PR e o merge na `master` dispara o apply automático do ambiente — que aplica **exatamente o plan salvo** no mesmo run. O merge verde também dispara o CD (`release.yml`); voltar atrás é sempre manual (workflows **Rollback** e **Destroy**).

> Gatilhos por evento, o fluxo dos jobs, os workflows de CD/rollback/destroy,
> os artefatos publicados, os secrets necessários e a configuração do
> SonarCloud estão em [docs/esteira.md](docs/esteira.md).

### ✅ Gates de qualidade

| Gate | Ferramenta |
| --- | --- |
| 🎨 Formatação | `blue` + `isort` |
| 🧱 Compilação | `python -m compileall` |
| 🔒 Segurança | `bandit` + `pip-audit` |
| 🧪 Testes | `pytest` (unit / integration / TAAC) |
| 🏛️ Arquitetura (TAAC) | `pytest -m taac` (estático sobre o HCL + live via boto3) |
| 🌍 Infraestrutura | `terraform fmt/validate` + `tflint` + `checkov` (árvore inteira) + plan |
| 📈 Qualidade de código | SonarCloud (Quality Gate com cobertura ≥ 90%) |

---

## 📁 Estrutura de Pastas

Os diretórios principais e o papel de cada um — o mapa completo código ↔ infra
está em [docs/arquitetura.md](docs/arquitetura.md#mapa-código--infra):

```text
.
├── .claude/                        # skills, agents, commands e lições
├── .github/workflows/              # ci, sonar, release (CD), rollback e destroy
├── docs/                           # arquitetura, esteira, operação e padrões
├── infra/terraform/
│   ├── bootstrap/                  # bucket do state remoto (apply único, manual)
│   ├── modules/                    # um módulo por componente; simulation/* separado
│   └── environments/prod/          # composição do ambiente de produção
├── scripts/
│   ├── athena/                     # aplica as views da gold e roda as queries
│   ├── bundle/                     # empacotamento das Lambdas e da API
│   ├── database/                   # seed do dataset Olist no RDS
│   ├── deploy/                     # precheck do bundle da API (gate do apply)
│   ├── release/                    # versionamento semver (CD)
│   └── teardown/                   # esvaziamento de buckets versionados
├── simulation/                     # fora da arquitetura: alimenta a Event API e o RDS
│   ├── db_seeder/                  # Lambda de seed do RDS
│   └── event_producer/             # Lambda que chama a Event API (não publica no SQS)
├── src/
│   ├── cold/                       # camada fria
│   │   ├── api_orders/             # API FastAPI async (data product Olist)
│   │   ├── lambda_ingest/          # Lambda EventBridge → API → raw
│   │   ├── glue_silver/            # job Glue raw → silver (Iceberg/DV)
│   │   └── athena_gold/            # DDL das views gold (dim_/fact_)
│   ├── hot/                        # camada quente
│   │   ├── api_events/             # Event API: valida o evento e publica no SQS
│   │   ├── lambda_raw_ingest/      # Lambda SQS → raw (batch item failures)
│   │   ├── glue_silver_microbatch/ # job Glue microbatch
│   │   └── athena_gold/            # DDL das views gold de eventos
│   ├── glue_silver_runtime/        # runtime compartilhado (specs DV + escrita Iceberg)
│   └── consumer/                   # queries analíticas sobre a gold (Athena)
├── tests/
│   ├── unit/                       # unitários
│   ├── integration/                # integração (marker `integration`)
│   └── taac/                       # testes de arquitetura (estático + live)
├── Makefile                        # fonte única dos comandos (local e esteira)
├── pyproject.toml
└── sonar-project.properties
```

---

## 🏁 Como Começar

```bash
# 1. Criar e ativar o ambiente virtual
python -m venv .venv && source .venv/bin/activate

# 2. Instalar o projeto e as dependências (extras prod)
pip install -e .[prod]

# 3. Instalar os hooks de pre-commit (espelham os gates do CI)
make install-hooks

# 4. Rodar o gate local completo antes de qualquer commit
make quality        # check-format + lint + security + test
```

> Para subir o ambiente na AWS do zero (bootstrap → apply → seed → silver →
> gold), o dia a dia e o teardown, siga o runbook em
> [docs/operacao.md](docs/operacao.md).

---

## 💡 Dicas de Implementação por Componente

### API FastAPI (camada fria)

- Definir contrato de dados versionado (schema + paginação).
- Incluir endpoint `/health` para o EventBridge/Lambda validar disponibilidade.
- Padronizar erros HTTP com `HTTPException` e correlation id nos logs.
- Dockerizar e criar script de deploy no EC2 (systemd ou supervisor).

### Lambda de ingestão batch

- Usar `boto3` para gravar no S3 com partições por `year/month/day/hour`.
- Implementar idempotência via checksum ou marker de última execução.
- Registrar métricas customizadas no CloudWatch (volume, latência, erros).

### Glue Silver com Iceberg

- Configurar `GlueContext` com catálogo Iceberg via Lake Formation.
- Definir estratégia de `MERGE INTO` para dados tardios.
- Agendar compactação periódica (`OPTIMIZE` + `VACUUM`) para controle de custo.
- Versionamento de schema habilitado por padrão no Iceberg.

### Athena Gold

- Criar views semânticas orientadas ao domínio de negócio.
- Versionar o DDL como arquivos `.sql` no repositório.
- Particionar a consulta para evitar full scan e reduzir custo.

### Camada quente (SQS + Lambda)

- Incluir `messageGroupId` e chave idempotente no payload do evento.
- Configurar Dead Letter Queue (DLQ) para eventos inválidos.
- Ajustar `batchSize` e `visibilityTimeout` do SQS conforme o throughput.

### Governança

- Lake Formation: criar `data lake locations`, registrar databases e aplicar `LF-tags` por domínio.
- CloudWatch: alarmes para `Lambda Errors`, `Glue Job Failures` e `SQS ApproximateNumberOfMessagesNotVisible`.

---

## 🔀 Dicas para o primeiro PR

- Implementar o caminho vertical mínimo da camada fria:
  `API → Lambda batch → S3 raw → Glue Silver → Athena Gold`.
- PR pequeno e focado, com testes unitários cobrindo o fluxo.
- Todos os checks da esteira devem estar verdes antes do merge.

---

## 📚 Referências

- [Terraform — Provider AWS](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Introdução a Testes Unitários](https://www.youtube.com/watch?v=pZvhZ-Lr-PE)
- [Introdução a Testes com Mock](https://www.youtube.com/watch?v=8uiMnwIkPYA)
- [Pytest Fixtures](https://www.youtube.com/watch?v=sidi9Z_IkLU)
- [Playlist Desenvolvimento de uma lib — importante para aprender técnicas de programação profissional](https://www.youtube.com/watch?v=R3hCkU4EXgY)
- [Curso FastAPI — gratuito](https://www.youtube.com/watch?v=ImhYlISeWPQ&list=PLOQgLBuj2-3KT9ZWvPmaGFQ0KjIez0403)
- [Curso FastAPI — pago](https://www.udemy.com/course/fastapi-apis-modernas-e-assincronas-com-python/?referralCode=6E89EB8C04280DEA5983)
- [Curso AWS — Essencial](https://www.udemy.com/course/amazon-web-services-essencial/?referralCode=835315E4467A40447001)
- [Programação Assíncrona](https://www.udemy.com/course/programacao-concorrente-e-assincrona-com-python/?referralCode=CDFB0EDDE8648B7DDE15)
- [Curso Design Patterns](https://www.udemy.com/course/padroes-de-projeto-com-python/?referralCode=0BC87A15DEC26B50505B)
- [Design Patterns — documentação](https://refactoring.guru/design-patterns)
- [Livro de Computação](https://www.amazon.com.br/Cientista-Computa%C3%A7%C3%A3o-Autodidata-Estruturas-Algoritmos/dp/8575228374/ref=sr_1_1?__mk_pt_BR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=21HYZK2Y40TWD&dib=eyJ2IjoiMSJ9.k-TIy9ot0B7FvP05Tc4SQHxMum3WXb7YClwTRyVdjLdYyTGU56pOTqp4D6AKHqTpybcc860XhceEnb9gjSYP3G-HZBTW_aENE3u78mZv4UkNBo7iv_JDTYRcLQM7ymxWt3EK7xPNMLNjkUpC0q94sk0l9L29gwMJEQX-Ms-WfMwHNvKvS80a3oilKmbu-0Gl.0p77zmiCSmrdfCuzAKvrYNGCUcq1FSRizMqQlPoKz6k&dib_tag=se&keywords=Cientista+da+Computa%C3%A7%C3%A3o+Autodidata&qid=1778100752&s=books&sprefix=cientista+da+computa%C3%A7%C3%A3o+autodidata%2Cstripbooks%2C217&sr=1-1)
- [Curso Esteira de Dados](https://cursos.alura.com.br/formacao-devops)
- [Testes de Integração](https://www.youtube.com/watch?v=qq8b1bck9AU)
- [Pipeline Terraform — usar como referência](https://www.youtube.com/watch?v=1TNAUW7_bC0)
- [Curso Docker](https://www.udemy.com/course/docker-essencial-para-o-desenvolvedor/?referralCode=4180ED98E508AEAAE5FF)
- [ShadowTraffic](https://shadowtraffic.io/)
- [Curso de Claude Code — recomendado](https://www.youtube.com/watch?v=MzMM5iV3GcU)

---

## 📄 Licença

Este projeto é licenciado sob a licença **MIT** — o texto completo está no
arquivo [`LICENSE`](LICENSE).
