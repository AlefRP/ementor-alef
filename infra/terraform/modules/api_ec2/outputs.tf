output "instance_id" {
  description = "ID da instância da API."
  value       = aws_instance.this.id
}

output "private_dns" {
  description = "DNS privado da API (consumido pela Lambda dentro da VPC)."
  value       = aws_instance.this.private_dns
}

output "base_url" {
  description = "URL HTTPS da API pelo IP privado fixo (casa com o SAN do cert)."
  value       = "https://${var.private_ip}:${var.api_port}"
}

output "ca_pem" {
  description = "Certificado (CA) self-signed p/ a Lambda verificar o TLS da API."
  value       = tls_self_signed_cert.api.cert_pem
}

output "private_ip" {
  description = "IP privado da instância."
  value       = aws_instance.this.private_ip
}

output "public_ip" {
  description = "IP público (apenas egress de deploy; ingress fica no SG)."
  value       = aws_instance.this.public_ip
}
