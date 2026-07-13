variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "service_name" {
  description = "Nome curto do serviço (ex.: api-cold, api-events) — vira o nome da unit systemd, do log de boot e da tag Name."
  type        = string
}

variable "service_description" {
  description = "Descrição da unit systemd (aparece no systemctl status)."
  type        = string
}

variable "app_module" {
  description = "Caminho de import do app ASGI servido pelo uvicorn (ex.: src.cold.api_orders.main:app)."
  type        = string
}

variable "service_env" {
  description = "Variáveis de ambiente da unit systemd (config da app; NUNCA segredos — a autenticação é por role da instância)."
  type        = map(string)
  default     = {}
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

variable "validate_bundle" {
  description = "Valida a existência do bundle no plan/apply. Desligue SOMENTE no destroy (o refresh lê data sources e um bundle ausente travaria o teardown)."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
