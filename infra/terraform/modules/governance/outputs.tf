output "lakeformation_data_access_role_arn" {
  description = "Role usada pelo Lake Formation para os data lake locations."
  value       = aws_iam_role.lakeformation_data_access.arn
}

output "lambda_ingest_cold_role_arn" {
  description = "Role da Lambda de ingestão batch (camada fria)."
  value       = aws_iam_role.lambda_ingest_cold.arn
}

output "lambda_ingest_hot_role_arn" {
  description = "Role da Lambda de ingestão de eventos (camada quente)."
  value       = aws_iam_role.lambda_ingest_hot.arn
}

output "glue_job_role_arn" {
  description = "Role do job Glue raw->silver."
  value       = aws_iam_role.glue_job.arn
}

output "analistas_user_names" {
  description = "Users IAM dos analistas (console; senhas criadas fora do Terraform)."
  value       = [for usuario in aws_iam_user.analista : usuario.name]
}

# O depends_on cria a aresta que o grafo não tem sozinho: a EC2 só referencia o
# NOME do profile (string imediata), mas a policy da role espera o RDS (~7 min,
# rds_resource_id no statement do rds-db:connect). Sem isso, num apply do zero a
# instância boota minutos antes da permissão existir, o user_data (roda 1x)
# falha no download do bundle e a API nasce morta e muda — nem o log de boot
# sobe, porque o ShipBootLog está na mesma policy ausente.
output "ec2_api_instance_profile_name" {
  description = "Instance profile das EC2 das APIs (pronto só após as policies)."
  value       = aws_iam_instance_profile.ec2_api.name

  depends_on = [
    aws_iam_role_policy.ec2_api,
    aws_iam_role_policy_attachment.ec2_api_ssm,
  ]
}
