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

output "s3_endpoint_prefix_list_id" {
  description = "Prefix list do gateway endpoint de S3."
  value       = aws_vpc_endpoint.s3.prefix_list_id
}
