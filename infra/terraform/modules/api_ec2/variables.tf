variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "subnet_id" {
  description = "Subnet PRIVADA onde a EC2 da API roda (sem IP público)."
  type        = string
}

variable "security_group_id" {
  description = "SG da API (ingress só da Lambda; ver módulo network)."
  type        = string
}

variable "private_ip" {
  description = "IP privado FIXO da EC2 — vira SAN do cert TLS self-signed e base da URL HTTPS que a Lambda verifica."
  type        = string
}

variable "instance_profile_name" {
  description = "Instance profile com a role ec2-api (módulo governance)."
  type        = string
}

variable "instance_type" {
  description = "Tipo da instância (free tier: t3.micro)."
  type        = string
  default     = "t3.micro"
}

variable "root_volume_gb" {
  description = "Tamanho do volume raiz (gp3, cifrado)."
  type        = number
  default     = 16
}

variable "api_port" {
  description = "Porta em que o uvicorn atende."
  type        = number
  default     = 8000
}

variable "artifacts_bucket" {
  description = "Bucket de artefatos com o bundle de deploy da API."
  type        = string
}

variable "bundle_key" {
  description = "Chave S3 do bundle (tar.gz com wheelhouse/)."
  type        = string
  default     = "api/api-bundle.tar.gz"
}

variable "pghost" {
  description = "Endpoint (host) do RDS PostgreSQL."
  type        = string
}

variable "pgport" {
  description = "Porta do RDS PostgreSQL."
  type        = number
  default     = 5432
}

variable "pgdatabase" {
  description = "Database do Olist no RDS."
  type        = string
  default     = "olist"
}

variable "pguser" {
  description = "Usuário do banco com grant rds_iam (IAM auth, sem senha)."
  type        = string
  default     = "api_reader"
}

variable "aws_region" {
  description = "Região usada na assinatura local do token IAM do RDS."
  type        = string
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
