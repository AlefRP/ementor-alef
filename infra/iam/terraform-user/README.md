# Permissões do user `terraform` (deployer sem ADM)

O user IAM `terraform` é quem roda o `terraform apply` (local e na esteira) e,
por consequência, o administrador do Lake Formation. Ele NÃO deve ter
`AdministratorAccess`: quem gerencia IAM sem cerca consegue se promover a
admin (cria uma role ampla e a assume). O desenho aqui troca o acesso de
admin por três anexos:

| Anexo | O que dá |
|---|---|
| `PowerUserAccess` (managed AWS) | todos os serviços da stack, MENOS IAM/Organizations/Account |
| `terraform-iam-scoped.json` | só o IAM que o deploy usa, preso ao prefixo `alef-rp-aws-lakehouse-*` |
| `terraform-region-guard.json` | Deny fora de `us-east-1` (exceto serviços globais) |

O que fica de fora (e é o ponto): criar/alterar users e access keys, billing,
configurações da conta, roles fora do namespace do projeto e qualquer região
que não seja a do lakehouse.

## Aplicação (manual, 1x — fora do Terraform)

Estes anexos são pré-requisito do próprio Terraform, então não moram no state
(mesma lógica do bootstrap do bucket de state). Ordem importa: anexe TUDO
antes de destacar o `AdministratorAccess`, senão o user se tranca.

```bash
CONTA=105299591310

aws iam create-policy \
  --policy-name alef-rp-aws-lakehouse-terraform-iam-scoped \
  --policy-document file://infra/iam/terraform-user/terraform-iam-scoped.json \
  --description "IAM do deploy preso ao prefixo do projeto (user terraform)"

aws iam create-policy \
  --policy-name alef-rp-aws-lakehouse-terraform-region-guard \
  --policy-document file://infra/iam/terraform-user/terraform-region-guard.json \
  --description "Deny fora de us-east-1 para o user terraform"

aws iam attach-user-policy --user-name terraform \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
aws iam attach-user-policy --user-name terraform \
  --policy-arn arn:aws:iam::$CONTA:policy/alef-rp-aws-lakehouse-terraform-iam-scoped
aws iam attach-user-policy --user-name terraform \
  --policy-arn arn:aws:iam::$CONTA:policy/alef-rp-aws-lakehouse-terraform-region-guard

# Só depois de validar (plan/refresh ok):
aws iam detach-user-policy --user-name terraform \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

## Aditivo v2 — users de consumo (analista)

O user `analista` (consumo humano via Athena/Lake Formation) vive no
Terraform (`modules/governance/analista.tf`). Para o deploy criá-lo, a policy
escopada ganhou três statements:

- **`UsersDeConsumoDoProjeto`** — gerenciar users `alef-rp-aws-lakehouse-*`
  (sem `PutUserPolicy`, de propósito: inline policy em user é escalação).
- **`AnexaSoPoliciesDoProjetoNosUsers`** — `AttachUserPolicy` só com policies
  do prefixo (condition `iam:PolicyARN`); sem isso daria para anexar
  `AdministratorAccess` num user novo.
- **`NaoEditaAsPropriasPolicies`** (Deny) — o `terraform` não altera as duas
  policies `terraform-*` (fecharia o ciclo de escalação por auto-edição).
  Depois deste aditivo, **editar estes JSONs exige root**.

Aplicação do aditivo (a última auto-edição permitida — ou root, se já ativo):

```bash
aws iam create-policy-version \
  --policy-arn arn:aws:iam::105299591310:policy/alef-rp-aws-lakehouse-terraform-iam-scoped \
  --policy-document file://infra/iam/terraform-user/terraform-iam-scoped.json \
  --set-as-default
```

Os analistas vêm da variável `analistas` do environment (ex.: `alef`,
`julio` → users `alef-rp-aws-lakehouse-prod-analista-alef` e
`...-analista-julio`). Cadastrar um novo = adicionar o nome à lista e
aplicar. Senha de console (root, 1x por analista): IAM → Users →
`...-analista-<nome>` → Security credentials → Enable console access.
A senha não passa pelo Terraform nem pelo shell.

## Recuperação

O user não consegue alterar os próprios anexos (não tem `iam:*UserPolicy` —
de propósito). Se uma permissão faltar e o plan quebrar: logue como **root**
no console, reanexe `AdministratorAccess`, corrija o JSON (novo
`create-policy-version --set-as-default`, que com o Deny do aditivo v2 só o
root executa) e destaque o admin de novo.

## Evoluções registradas (não aplicadas)

- **Permissions boundary** obrigatória nas roles criadas pelo Terraform
  (condition `iam:PermissionsBoundary` no `CreateRole`) — fecha a escalação
  residual via role prefixada com policy ampla.
- **OIDC no GitHub Actions** — troca as access keys de longa duração da
  esteira por role federada; maior redução de superfície disponível.
