---
name: taac-testing
description: >-
  Use ao escrever ou alterar testes TAAC (testes automatizados de arquitetura em
  cloud) em tests/taac/ — validações estáticas sobre o código Terraform (sem AWS)
  e validações live da infra provisionada via boto3 (com skip gracioso sem
  credenciais/infra). Acione em "TAAC", "teste de arquitetura", "validar infra",
  "teste do terraform", "conformidade da infra".
---

# TAAC — Testes de Arquitetura em Cloud

Dois níveis, ambos em `tests/taac/` com `pytestmark = pytest.mark.taac`
(**obrigatório** — `make test-taac` seleciona por marker; teste sem marker é
silenciosamente ignorado = verde falso).

## Nível 1 — Estático (sem AWS; roda em todo CI)

Valida **regras de arquitetura no código Terraform** lendo os `.tf` como texto
estruturado. Não exige credenciais nem infra aplicada — é gate imediato.

Regras que este repo exige (espelham os critérios de aceitação das stories):
- Todo `aws_s3_bucket` tem `aws_s3_bucket_public_access_block` com os 4 flags `true`.
- Nenhuma policy IAM própria com `"*"` em actions/resources isolado (least-privilege).
- RDS: `publicly_accessible` nunca `true`, `storage_encrypted = true`,
  `manage_master_user_password` presente (sem senha hardcoded).
- SQS: `sqs_managed_sse_enabled = true` em toda fila.
- Backend `s3` com `encrypt = true` e `use_lockfile = true`.
- Buckets raw e silver registrados como `aws_lakeformation_resource`.

Use o helper de parsing de `tests/taac/conftest.py` (`terraform_blocks`) — extração
de blocos por contagem de chaves. Não adicione dependência de parser HCL.

## Nível 2 — Live (boto3; valida a conta real)

Confere que a infra **aplicada** cumpre a arquitetura. Regras de robustez:

```python
import pytest

boto3 = pytest.importorskip("boto3")
pytestmark = pytest.mark.taac

# Skip por MÓDULO se não houver credenciais (CI matrix não tem):
if not os.environ.get("AWS_ACCESS_KEY_ID"):
    pytest.skip("sem credenciais AWS", allow_module_level=True)
```

- Recurso ainda não aplicado (404/NoSuchEntity) → `pytest.skip("infra não aplicada")`,
  nunca falha — o teste vira gate real após o primeiro apply.
- Nomes de recursos vêm do prefixo `ementor-lakehouse-prod` (variável de ambiente
  `TAAC_PREFIX` para sobrescrever).
- Cheques live essenciais: BPA dos buckets via `s3.get_public_access_block`;
  SQS SSE via `get_queue_attributes`; RDS `PubliclyAccessible`/`StorageEncrypted`
  via `describe_db_instances`; roles sem `"*"` via `iam.list_role_policies` +
  `get_role_policy`; locations via `lakeformation.list_resources`.

## Comandos

```bash
pytest -m taac --collect-only -q   # confere que TODOS os testes têm o marker
make test-taac                     # roda a suíte TAAC
```

Ver também: agent `test-engineer`, skills `terraform-aws-module` e
`lakehouse-governance` (as regras validadas nascem lá).
