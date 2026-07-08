output "endpoint" {
  description = "Endpoint (host:porta) do PostgreSQL."
  value       = aws_db_instance.this.endpoint
}

output "address" {
  description = "Hostname do PostgreSQL (para o seed e para a API)."
  value       = aws_db_instance.this.address
}

output "db_name" {
  description = "Database inicial."
  value       = aws_db_instance.this.db_name
}

output "master_username" {
  description = "Usuário master."
  value       = aws_db_instance.this.username
}

output "master_user_secret_arn" {
  description = "ARN do secret (Secrets Manager) com a senha do master."
  value       = one(aws_db_instance.this.master_user_secret[*].secret_arn)
}

output "instance_arn" {
  description = "ARN da instância RDS."
  value       = aws_db_instance.this.arn
}

output "resource_id" {
  description = "Resource id (dbi-*) usado no ARN de rds-db:connect (IAM auth)."
  value       = aws_db_instance.this.resource_id
}

output "port" {
  description = "Porta do PostgreSQL."
  value       = aws_db_instance.this.port
}
