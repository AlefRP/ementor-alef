# EC2 das APIs do lakehouse — postura 100% privada: subnet privada, sem IP
# público e sem NAT. O bootstrap é offline: dnf usa os repositórios do AL2023
# servidos via S3 (gateway endpoint) e o código chega como bundle de wheels do
# bucket de artefatos. Nenhum segredo em runtime: a instância se autentica pela
# role (token IAM no RDS na fria, SendMessage no SQS na quente).
#
# O módulo é genérico e serve as DUAS APIs (`service_name` + `app_module` +
# `service_env`): fria (api_orders -> RDS) e quente (api_events -> SQS). Elas
# compartilham o mesmo bundle de deploy, porque são o mesmo pacote Python.

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# O user_data instala o bundle no PRIMEIRO boot e nunca roda de novo: sem o
# bundle publicado, a instância nasceria quebrada e silenciosa. Este data
# source corta o problema na raiz: o apply falha aqui, antes de criar a EC2.
# `make tf-apply` garante a pré-condição via scripts/deploy/ensure_api_bundle.py
# (no bootstrap do zero cria o storage primeiro e publica o bundle antes do
# apply completo). O etag entra no user_data, então bundle novo => user_data
# muda => a instância é substituída no próximo apply.
# Data sources também são lidos no refresh do DESTROY: sem o count abaixo,
# bundle ausente tornaria a infra indestrutível (os alvos tf-destroy e
# tf-plan-out DESTROY=1 passam validate_bundle=false).
data "aws_s3_object" "bundle" {
  count = var.validate_bundle ? 1 : 0

  bucket = var.artifacts_bucket
  key    = var.bundle_key
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
    artifacts_bucket    = var.artifacts_bucket
    bundle_key          = var.bundle_key
    bundle_etag         = var.validate_bundle ? data.aws_s3_object.bundle[0].etag : "unverified"
    api_port            = var.api_port
    service_name        = var.service_name
    service_description = var.service_description
    app_module          = var.app_module
    service_env         = var.service_env
    tls_cert_pem        = tls_self_signed_cert.api.cert_pem
    tls_key_pem         = tls_private_key.api.private_key_pem
  })
  user_data_replace_on_change = true

  tags = merge(var.tags, { Name = "${var.prefix}-${var.service_name}" })
}
