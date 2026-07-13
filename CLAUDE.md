# AWS Lakehouse Mentoria

Data lakehouse educacional na AWS: camada **fria** (FastAPI/EC2 → Lambda/EventBridge → S3 raw → Glue/Iceberg → silver → Athena gold) e **quente** (API/EC2 → SQS → Lambda → raw → Glue microbatch → silver → gold). Governança: Lake Formation + CloudWatch. Fonte de dados: dataset **Olist** (e-commerce BR) no RDS PostgreSQL.

## Mapa

**Fronteira que organiza o repo:** a arquitetura começa **na Event API** (quente) e **no RDS** (frio). Tudo que *alimenta* essas fronteiras é simulação e não se mistura com o lakehouse. Quem publica no SQS é a Event API — a simulação apenas a chama por HTTP.

- `src/cold|hot/` — **arquitetura**, código de produção. `cold/api_orders` (RDS→serving), `cold/lambda_ingest` (API→raw), `hot/api_events` (Event API na EC2: valida o evento e publica no SQS), `hot/lambda_raw_ingest` (consome SQS→raw), `cold/glue_silver` e `hot/glue_silver_microbatch` (entrypoints dos jobs raw→silver), `cold/athena_gold` e `hot/athena_gold` (DDL das views da gold)
- `src/consumer/` — queries analíticas sobre a gold (a ponta final do desenho)
- `src/glue_silver_runtime/` — runtime compartilhado dos jobs Glue silver (specs Data Vault + escrita Iceberg); vai no zip via `--extra-py-files`, por isso os imports são flat (`known_first_party` no pyproject)
- **A gold é código, não state:** o Terraform cria database + workgroup; as views (`CREATE OR REPLACE VIEW`) são aplicadas por `scripts/athena/apply_views.py` (`make athena-gold`), e a esteira roda isso no merge, após o apply.
- `simulation/` — **fora da arquitetura**: Lambdas que alimentam a Event API (`event_producer`, via HTTP) e o RDS (`db_seeder`) + os geradores Faker. Vai no zip das Lambdas, então passa por blue/isort/bandit, mas **fica fora da cobertura e sem testes** (é simulação, não lógica de negócio)
- `tests/unit|integration|taac/` — markers `integration` e `taac`
- `infra/terraform/modules/` — mesma fronteira: `simulation/{event_producer,db_seeder}` separados dos módulos da arquitetura. `api_ec2` é genérico e serve as DUAS APIs (`service_name` + `app_module` + `service_env`)
- `scripts/database/` — seed do Olist no RDS; `scripts/bundle/` — empacotamento das Lambdas/API; `scripts/athena/` — aplica a gold e roda as queries do consumer
- `docs/` — padrões do projeto: testes AAA (`padrao-de-testes.md`) e API (`padrao-de-api.md`)
- `.claude/` — skills, agents, commands, hooks, lessons (ver `.claude/README.md`)

## Comandos

```bash
make quality        # check-format + lint + security + test (gate local completo)
make test-cov       # cobertura (gate SonarCloud: >= 90%)
make test-taac      # testes de arquitetura (TAAC)
make athena-gold    # aplica as views da gold (a esteira roda no merge)
make athena-gold-dry-run                # renderiza o DDL sem tocar a AWS
make athena-query QUERY=<nome>          # roda uma query de src/consumer
make tf-validate tf-lint tf-security   # gates Terraform sem AWS
make tf-bootstrap-apply                # 1x: cria o bucket de state remoto
make tf-plan TF_ENV=prod               # autentica na AWS — só quando necessário
make tf-apply TF_ENV=prod              # apply manual (bootstrap/exceção; a esteira aplica no merge à master)
make tf-destroy FORCE=1                # teardown total (FORCE arma force_destroy e esvazia buckets)
```

## Convenções

- Python ≥ 3.11; **blue** (88 col, aspas **simples**; duplas só em docstrings) + **isort** (profile black). Testes: `test_<unidade>_<cenario>`.
- **Funções com nomes em PT-BR** (ex.: `montar_hub`, `datasets_selecionados`); nomes de tabelas/colunas seguem o dataset Olist e o padrão DV em inglês (`hub_customer`, `hashdiff`). Testes no padrão **AAA** com seções comentadas (`# Arrange` / `# Act` / `# Assert`).
- **Nunca commite sem rodar os formatadores.** O Python local (3.14) quebra o blue; use `uv run --python 3.11 --with blue==0.9.1 --no-project blue src simulation tests` (idem isort) antes de todo commit.
- Paths S3 sempre particionados `year/month/day`. Logging estruturado JSON, nunca `print`.
- Sem credenciais/segredos no código — IAM roles + env vars. IAM sempre least-privilege (nunca `Action:"*"`).
- Terraform: módulos em `modules/`, composição em `environments/`; **nunca rode `terraform apply`** (a esteira aplica no merge à master — plan no PR, apply automático; local só bootstrap/exceção).
- Não comente/documente código que você não alterou. **Todo texto autoral em PT-BR**: docs, docstrings, comentários, descriptions de Terraform e commits (`tipo(escopo): descricao`).

## Protocolo de aprendizado (obrigatório)

1. **Antes** de tarefa não-trivial: leia `.claude/lessons/LESSONS.md` e aplique as lições do tipo relevante.
2. **Sempre que cometer um erro** (tool falhou, gate quebrou, retrabalho, correção do usuário): registre a lição via `/lesson` ou editando `LESSONS.md` — entrada curta: sintoma → causa raiz → regra.
3. Lição repetida 2x → promova a regra para a skill/agent correspondente.

## Building blocks

Skills: `terraform-aws-module`, `lakehouse-governance`, `glue-iceberg-job`, `aws-lambda-ingestion`, `taac-testing`.
Agents: `data-engineer`, `spark-glue-engineer`, `software-engineer`, `iac-security-reviewer`, `cicd-engineer`, `test-engineer`.
Commands: `/quality`, `/tf-plan`, `/coverage`, `/lesson`.
