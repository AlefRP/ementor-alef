variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "handler_source" {
  description = "Caminho do handler.py autocontido (zipado pelo módulo)."
  type        = string
}

variable "role_arn" {
  description = "Role de execução (lambda-ingest-cold, módulo governance)."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets privadas onde a Lambda roda (VPC)."
  type        = list(string)
}

variable "security_group_id" {
  description = "SG da Lambda (egress só para API e S3; módulo network)."
  type        = string
}

variable "raw_bucket" {
  description = "Nome do bucket da camada raw."
  type        = string
}

variable "api_base_url" {
  description = "URL privada da API de pedidos (https://<ip-privado>:<porta>)."
  type        = string
}

variable "api_ca_pem" {
  description = "Certificado (CA) self-signed da API, embarcado no zip p/ verificar o TLS."
  type        = string
}

variable "schedule_expression" {
  description = "Agenda do EventBridge (rate/cron)."
  type        = string
  default     = "rate(1 day)"
}

variable "dataset" {
  description = "Dataset ingerido (prefixo na raw e no marker)."
  type        = string
  default     = "orders"
}

variable "page_size" {
  description = "Tamanho de página pedido à API."
  type        = number
  default     = 500
}

variable "max_pages" {
  description = "Máximo de páginas por execução (protege o timeout)."
  type        = number
  default     = 50
}

variable "timeout_seconds" {
  description = "Timeout da função."
  type        = number
  default     = 300
}

variable "reserved_concurrency" {
  description = "Concorrência reservada (-1 = sem reserva). Padrão -1: contas free tier limitam a concorrência total a 10 e a AWS exige o pool não-reservado >= 10, então qualquer reserva falha. Suba a quota (Service Quotas) p/ usar > 0."
  type        = number
  default     = -1
}

variable "memory_mb" {
  description = "Memória da função."
  type        = number
  default     = 256
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
