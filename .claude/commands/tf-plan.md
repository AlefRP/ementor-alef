---
description: Roda os checks de Terraform (fmt/validate/tflint/checkov) e o plan de um ambiente, e resume a mudança de infra.
argument-hint: "[env] (default: prod)"
allowed-tools: Bash(make:*), Bash(terraform:*), Bash(tflint:*), Bash(checkov:*)
---

Valide e planeje a infraestrutura do ambiente **${ARGUMENTS:-prod}** (`infra/terraform/environments/${ARGUMENTS:-prod}`), espelhando o job `terraform` do CI.

Rode primeiro os gates que NÃO tocam a AWS:

```bash
make tf-fmt-check TF_ENV=${ARGUMENTS:-prod}
make tf-validate  TF_ENV=${ARGUMENTS:-prod}
make tf-lint      TF_ENV=${ARGUMENTS:-prod}
make tf-security  TF_ENV=${ARGUMENTS:-prod}
```

Se todos passarem, rode o plan (isto **autentica na AWS via STS** — confirme antes se as credenciais `AWS_*` estão no ambiente):

```bash
make tf-plan TF_ENV=${ARGUMENTS:-prod}
```

Ao final:
- Resuma o que o plan **cria/altera/destrói** (contagem + recursos mais relevantes).
- Destaque qualquer finding de checkov/tflint pendente.
- **Nunca** rode `terraform apply` — neste repo o apply é manual/rollback.
- Se faltarem credenciais ou o backend não estiver configurado, diga exatamente o que falta.
