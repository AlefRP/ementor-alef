output "vpc_id" {
  description = "ID da VPC do lakehouse."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Subnets públicas (EC2 das APIs)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Subnets privadas (RDS)."
  value       = aws_subnet.private[*].id
}

output "private_subnet_cidrs" {
  description = "CIDRs das subnets privadas (p/ IP fixo da API no cert TLS)."
  value       = aws_subnet.private[*].cidr_block
}

output "api_security_group_id" {
  description = "SG das EC2 de API."
  value       = aws_security_group.api.id
}

output "database_security_group_id" {
  description = "SG do RDS."
  value       = aws_security_group.database.id
}

output "lambda_ingest_security_group_id" {
  description = "SG da Lambda de ingestão fria (VPC)."
  value       = aws_security_group.lambda_ingest.id
}

output "lambda_hot_security_group_id" {
  description = "SG da Lambda de ingestão quente (VPC)."
  value       = aws_security_group.lambda_hot.id
}

output "lambda_db_seeder_security_group_id" {
  description = "SG da Lambda de seed do banco (simulação, VPC)."
  value       = aws_security_group.lambda_db_seeder.id
}

output "lambda_event_producer_security_group_id" {
  description = "SG da Lambda produtora de eventos (simulação, VPC) — chama a Event API."
  value       = aws_security_group.lambda_event_producer.id
}

output "s3_endpoint_prefix_list_id" {
  description = "Prefix list do gateway endpoint de S3."
  value       = aws_vpc_endpoint.s3.prefix_list_id
}
