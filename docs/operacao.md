# Operação — runbook do ambiente

> Parte da documentação do projeto — veja o [README](../README.md) para a visão
> geral, a [arquitetura](arquitetura.md) e a [esteira CI/CD](esteira.md).

Todos os comandos são alvos do [`Makefile`](../Makefile) — a mesma fonte que a
esteira usa. Este runbook cobre: preparar a máquina, subir o ambiente do zero,
o dia a dia e o teardown.

## Pré-requisitos

- Python ≥ 3.11, Terraform ≥ 1.15.6, AWS CLI e `make`.
- Credenciais AWS de um **IAM user dedicado** (nunca root — o Lake Formation
  inclusive recusa root como admin do data lake).
- `TF_ENV` escolhe o ambiente (default `prod`):
  `make tf-plan TF_ENV=prod` → `infra/terraform/environments/prod/`.

## Setup local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .[prod]
make install-hooks     # pre-commit espelhando os gates do CI
```

## Ciclo de desenvolvimento

```bash
make quality           # gate local completo: check-format + lint + security + test
make test-cov          # cobertura (gate SonarCloud: >= 90%)
make test-taac         # testes de arquitetura (estáticos + live com skip gracioso)

make tf-validate tf-lint tf-security   # gates Terraform sem AWS
make athena-gold-dry-run               # renderiza o DDL da gold sem tocar a AWS
```

> O Python local mais novo (3.14) quebra o blue. Antes de todo commit:
> `uv run --python 3.11 --with blue==0.9.1 --no-project blue src simulation tests`
> (idem isort) — ou simplesmente `make format` num venv 3.11.

O caminho normal para mudar a infra é **PR → merge**: o plan aparece no PR e o
merge na `master` aplica sozinho ([esteira](esteira.md)). `terraform apply`
local é exceção (bootstrap, laboratório).

## Subir o ambiente do zero

```bash
# 1. State remoto (uma única vez, state local -> cria o bucket de backend)
make tf-bootstrap-apply

# 2. Infra completa. O alvo encadeia: bundles da simulação, tf-ensure-bundle
#    (builda e publica o bundle da API no S3 — em bootstrap do zero cria o
#    storage primeiro, em duas fases) e o apply com confirmação.
make tf-apply TF_ENV=prod

# 3. Semear o Olist no RDS (invoca a Lambda db_seeder; idempotente)
make seed-db

# 4. Primeira carga fria da raw (RDS -> API fria -> S3). Só a camada fria tem
#    esse bootstrap: ela tem backlog histórico para paginar. A quente é reativa
#    (o event_producer agendado já alimenta a Event API sozinho).
make raw-bootstrap

# 5. Materializar a silver (dispara os jobs Glue cold/hot e espera o SUCCEEDED)
make silver-run

# 6. Aplicar as views da gold (CREATE OR REPLACE VIEW, idempotente)
make athena-gold

# 7. Conferir a ponta final
make athena-query QUERY=01_receita_por_categoria   # sem QUERY, lista as opções
```

Observações:

- O `make tf-apply` já tenta um `raw-bootstrap` ao final; num ambiente recém
  criado o RDS ainda está vazio, por isso o passo 4 repete a carga **depois**
  do seed.
- Fora do bootstrap, os jobs são **agendados**: a Lambda fria por EventBridge,
  os jobs Glue por EventBridge Scheduler e o producer de eventos pelo próprio
  agendamento da simulação.

## Dia a dia

| Preciso de... | Comando |
| --- | --- |
| Deploy de código/infra | Merge na `master` (a esteira faz bundle → apply → silver → gold) |
| Deploy manual do checkout local | `make tf-apply` (republica o bundle: etag novo → user_data novo → EC2 substituída) |
| Rodar uma query do consumer | `make athena-query QUERY=<nome>` |
| Reprocessar a silver | `make silver-run` (seguro: merges idempotentes por hash key/hashdiff) |
| Reaplicar as views da gold | `make athena-gold` |
| Ver os outputs do Terraform | `make tf-output` |

## Diagnóstico

- **EC2 privadas** não têm SSH: use **SSM Session Manager**. O log de boot
  (user_data) também é enviado ao S3 — se a API não subiu, comece por ele.
- **CloudWatch**: todo componente tem log group próprio com logging estruturado
  em JSON. Os **alarmes** cobrem erro nas Lambdas de ingestão, mensagem na DLQ,
  backlog envelhecendo na fila e status check das EC2; falha de job Glue chega
  por e-mail (EventBridge → SNS).
- **Gate vermelho no CI** em arquivo que você não tocou: confira antes
  `git status --short` e `git diff HEAD -- <arquivo>` — pode ser trabalho em
  andamento de outra pessoa na árvore.

## Rollback

Workflow manual **Rollback** no GitHub Actions: escolhe uma tag/SHA antigo,
republica o bundle daquele ref e roda em modo `plan` (simular) ou `apply`
(executar). O plan fica como artefato de auditoria. Detalhes em
[esteira.md](esteira.md#-cd-e-operações-manuais).

## Teardown

```bash
make tf-destroy-precheck   # falha em segundos se houver dado que travaria o destroy
make tf-destroy            # ambiente sem dados nos buckets
make tf-destroy FORCE=1    # ambiente com dados (o caso normal)
```

O `FORCE=1` encadeia o `tf-force-arm`, que resolve as duas pegadinhas de
teardown conhecidas do projeto:

1. Esvazia os buckets **versionados** (raw/silver/artifacts) via API — o
   `force_destroy` do Terraform não remove versões nem delete markers — e limpa
   o histórico do workgroup do Athena.
2. Grava `force_destroy=true` **no state** desses recursos antes do destroy
   (o provider lê o flag do state ao deletar; passar `-var` direto no destroy
   não tem efeito).

O bucket de state (bootstrap) fica de pé por design (`prevent_destroy`). Sem
`FORCE`, um destroy com dados rodaria ~20 minutos e falharia no último recurso
(`BucketNotEmpty`) — por isso o precheck existe e roda automaticamente.

Também existe o workflow manual **Destroy** na esteira, com confirmação
digitada e a mesma opção `force` ([esteira.md](esteira.md#-cd-e-operações-manuais)).
