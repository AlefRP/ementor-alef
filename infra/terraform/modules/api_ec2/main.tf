# EC2 da API de data product (camada fria) — postura 100% privada: subnet
# privada, sem IP público e sem NAT. O bootstrap é offline: dnf usa os
# repositórios do AL2023 servidos via S3 (gateway endpoint) e o código chega
# como bundle de wheels do bucket de artefatos. A senha do RDS não existe em
# runtime: autenticação por token IAM assinado localmente (role ec2-api).

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# TLS self-signed (custo zero) para criptografar o tráfego Lambda -> API dentro
# da VPC. O SAN é o IP privado FIXO da EC2, então a Lambda chama https://<ip> e
# verifica o certificado contra a CA embarcada no seu zip (sem depender do DNS
# gerado só após o boot). Para um lab privado, self-signed encripta o tráfego
# sem o custo de ACM Private CA / ALB.
resource "tls_private_key" "api" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "api" {
  private_key_pem = tls_private_key.api.private_key_pem

  subject {
    common_name  = var.private_ip
    organization = var.prefix
  }

  ip_addresses          = [var.private_ip]
  validity_period_hours = 87600 # 10 anos: lab; rotação manual via replace
  early_renewal_hours   = 720

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

resource "aws_instance" "this" {
  #checkov:skip=CKV_AWS_126: monitoring detalhado do CloudWatch é pago; métricas básicas atendem a mentoria
  ami                         = nonsensitive(data.aws_ssm_parameter.al2023_ami.value)
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  private_ip                  = var.private_ip # fixo: casa com o SAN do cert TLS
  vpc_security_group_ids      = [var.security_group_id]
  iam_instance_profile        = var.instance_profile_name
  associate_public_ip_address = false # postura privada: sem IP público, sempre
  ebs_optimized               = true

  # IMDSv2 obrigatório (bloqueia SSRF de roubo de credenciais via IMDSv1).
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
    encrypted   = true
  }

  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    artifacts_bucket = var.artifacts_bucket
    bundle_key       = var.bundle_key
    api_port         = var.api_port
    pghost           = var.pghost
    pgport           = var.pgport
    pgdatabase       = var.pgdatabase
    pguser           = var.pguser
    aws_region       = var.aws_region
    tls_cert_pem     = tls_self_signed_cert.api.cert_pem
    tls_key_pem      = tls_private_key.api.private_key_pem
  })
  user_data_replace_on_change = true

  tags = merge(var.tags, { Name = "${var.prefix}-api-cold" })
}
