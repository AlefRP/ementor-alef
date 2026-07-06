# Building blocks do Claude Code — Lakehouse Mentoria

Blocos de construção que ensinam o Claude Code a trabalhar neste repo seguindo as
convenções da arquitetura (camadas fria/quente, raw→silver→gold, Terraform/AWS) e as
melhores práticas de referência da área. Fundamentação:

- **Fundamentals of Data Engineering** — Joe Reis & Matt Housley (ciclo de vida +
  *undercurrents*: segurança, gestão de dados, DataOps, arquitetura, orquestração, eng. de software).
- **PySpark Best Practices** (docs oficiais Apache Spark) — particionamento, broadcast join, arquivos 128 MB–1 GB.
- **AWS Prescriptive Guidance — Terraform AWS Provider Best Practices** + IAM least-privilege.
- Estrutura *diagnose-first* inspirada na `terraform-skill` (Anton Babenko) e nos subagents do VoltAgent.

## Skills (`.claude/skills/`) — acionadas automaticamente pelo contexto

| Skill | Quando dispara |
|---|---|
| **terraform-aws-module** | Criar/alterar/revisar Terraform em `infra/terraform/**` — gates fmt/validate/tflint/checkov, state remoto, least-privilege. |
| **lakehouse-governance** | Lake Formation (registrar raw/silver como Data Lake Locations) + roles IAM Glue/Lambda/EC2 com menor privilégio. |
| **glue-iceberg-job** | Jobs Glue/PySpark raw→silver em Iceberg; particionamento e tuning de performance. |
| **aws-lambda-ingestion** | Lambdas de ingestão (EventBridge/SQS) → raw S3 particionada por `year/month/day`. |
| **taac-testing** | Testes de arquitetura em cloud (`tests/taac/`): estáticos sobre o HCL + live via boto3 com skip gracioso. |

## Agents (`.claude/agents/`) — invoque com o subagent

| Agent | Uso |
|---|---|
| **data-engineer** | Projetar/implementar componentes de pipeline (Python, Glue, Lambda, modelagem). |
| **iac-security-reviewer** | Revisar Terraform (read-only): least-privilege, checkov/tflint, Block Public Access, segredos. |
| **cicd-engineer** | Criar/depurar a esteira (GitHub Actions, gates, Sonar, terraform plan, rollback, artefatos). |
| **test-engineer** | Escrever/melhorar testes (unit, integration, TAAC) e fechar lacunas rumo à cobertura ≥ 80%. |

## Commands (`.claude/commands/`) — slash commands

| Comando | O que faz |
|---|---|
| `/quality [alvo]` | Roda o gate local (format, lint, security, testes) e resume falhas. |
| `/tf-plan [env]` | fmt/validate/tflint/checkov + `terraform plan` do ambiente; resume a mudança de infra. |
| `/coverage` | Testes com cobertura e verifica o gate de **≥ 80%** (critério do SonarCloud). |
| `/lesson [erro]` | Registra uma lição aprendida (sintoma → causa raiz → regra) no banco de lições. |

## Banco de lições (`.claude/lessons/LESSONS.md`)

Memória de erros do projeto: cada erro vira uma entrada curta (sintoma → causa
raiz → regra). O `CLAUDE.md` da raiz obriga: **consultar antes** de tarefas
não-triviais e **registrar depois** de qualquer erro. Lição repetida 2x é
promovida para a skill/agent correspondente. É assim que o Claude "aprende" ao
longo do projeto — versionado e visível no git.

## Hook (`.claude/hooks/format_on_write.py`)

Formata todo arquivo recém-escrito para casar com os gates do CI: `.py` → **blue + isort**,
`.tf` → **terraform fmt**. É *advisory* (nunca falha a operação; no-op se a ferramenta não
estiver instalada) e multiplataforma (só requer Python 3.11+).

> ⚠️ **Wiring manual necessário.** Adicionar hooks ao `settings.json` é uma mudança
> sensível, então o Claude não a aplica sozinho. Cole o bloco abaixo em
> `.claude/settings.json` (chave `hooks`, no mesmo nível de `permissions`):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          { "type": "command", "command": "python .claude/hooks/format_on_write.py" }
        ]
      }
    ]
  }
}
```

Para reduzir prompts de permissão dos comandos, você pode ainda adicionar ao
`permissions.allow`: `Bash(make:*)`, `Bash(pytest:*)`, `Bash(terraform fmt:*)`,
`Bash(terraform validate:*)`, `Bash(tflint:*)`, `Bash(checkov:*)`.

---

Os building blocks **codificam as convenções do repo** (blue 88 col, isort profile black,
path `year/month/day`, `src/` para produção, cobertura ≥ 80%, sem credenciais no código) —
mantenha-os alinhados a `.github/copilot-instructions.md`, ao `Makefile` e à esteira em
`.github/workflows/` conforme o projeto evolui.
