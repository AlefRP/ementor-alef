# Smoke de integração com a AWS: o `terraform plan` força uma chamada STS
# (GetCallerIdentity), validando credenciais e conectividade com a conta antes
# de qualquer recurso real existir. Expanda este arquivo conforme os
# componentes do lakehouse forem implementados.
data "aws_caller_identity" "current" {}

output "aws_account_id" {
  description = "Conta AWS autenticada durante o plan (valida a integração)."
  value       = data.aws_caller_identity.current.account_id
}
