# AWS Lakehouse Mentoria

Data lakehouse educacional na AWS: camada **fria** (FastAPI/EC2 → Lambda/EventBridge → S3 raw → Glue/Iceberg → silver → Athena gold) e **quente** (API/EC2 → SQS → Lambda → raw → Glue microbatch → silver → gold). Governança: Lake Formation + CloudWatch. Fonte de dados: dataset **Olist** (e-commerce BR) no RDS PostgreSQL.

## Mapa

- `src/cold|hot|consumer/` — código de produção (só aqui)
- `tests/unit|integration|taac/` — markers `integration` e `taac`
- `infra/terraform/` — `bootstrap/` (state remoto, apply único), `modules/`, `environments/prod/`
- `scripts/database/` — seed único do Olist no RDS
- `.claude/` — skills, agents, commands, hooks, lessons (ver `.claude/README.md`)

## Comandos

```bash
make quality        # check-format + lint + security + test (gate local completo)
make test-cov       # cobertura (gate SonarCloud: >= 90%)
make test-taac      # testes de arquitetura (TAAC)
make tf-validate tf-lint tf-security   # gates Terraform sem AWS
make tf-bootstrap-apply                # 1x: cria o bucket de state remoto
make tf-plan TF_ENV=prod               # autentica na AWS — só quando necessário
make tf-apply TF_ENV=prod              # apply manual (esteira só faz plan)
make tf-destroy FORCE=1                # teardown total (FORCE esvazia buckets)
```

## Convenções

- Python ≥ 3.11; **blue** (88 col, aspas **simples**; duplas só em docstrings) + **isort** (profile black). Testes: `test_<unidade>_<cenario>`.
- Paths S3 sempre particionados `year/month/day`. Logging estruturado JSON, nunca `print`.
- Sem credenciais/segredos no código — IAM roles + env vars. IAM sempre least-privilege (nunca `Action:"*"`).
- Terraform: módulos em `modules/`, composição em `environments/`; **nunca rode `terraform apply`** (apply é manual; a esteira só faz plan).
- Não comente/documente código que você não alterou. Docs e commits em PT-BR (`tipo(escopo): descricao`).

## Protocolo de aprendizado (obrigatório)

1. **Antes** de tarefa não-trivial: leia `.claude/lessons/LESSONS.md` e aplique as lições do tipo relevante.
2. **Sempre que cometer um erro** (tool falhou, gate quebrou, retrabalho, correção do usuário): registre a lição via `/lesson` ou editando `LESSONS.md` — entrada curta: sintoma → causa raiz → regra.
3. Lição repetida 2x → promova a regra para a skill/agent correspondente.

## Building blocks

Skills: `terraform-aws-module`, `lakehouse-governance`, `glue-iceberg-job`, `aws-lambda-ingestion`, `taac-testing`.
Agents: `data-engineer`, `software-engineer`, `iac-security-reviewer`, `cicd-engineer`, `test-engineer`.
Commands: `/quality`, `/tf-plan`, `/coverage`, `/lesson`.
