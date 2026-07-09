variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: alef-rp-aws-lakehouse-prod)."
  type        = string
}

variable "ingest_source" {
  description = "Caminho do handler.py da ingestão (zipado pelo módulo)."
  type        = string
}

variable "ingest_role_arn" {
  description = "Role da Lambda de ingestão quente (módulo governance)."
  type        = string
}

variable "events_queue_arn" {
  description = "ARN da fila de eventos (event source mapping)."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets privadas da Lambda de ingestão (VPC)."
  type        = list(string)
}

variable "security_group_id" {
  description = "SG da Lambda quente (egress só S3; módulo network)."
  type        = string
}

variable "raw_bucket" {
  description = "Nome do bucket da camada raw."
  type        = string
}

variable "dataset" {
  description = "Dataset dos eventos (prefixo na raw)."
  type        = string
  default     = "events"
}

variable "batch_size" {
  description = "Tamanho do lote entregue pelo SQS à ingestão."
  type        = number
  default     = 10
}

variable "ingest_max_concurrency" {
  description = "Concorrência máxima da ingestão (mínimo 2 no SQS mapping)."
  type        = number
  default     = 2
}

variable "ingest_reserved_concurrency" {
  description = "Concorrência reservada da ingestão quente (-1 = sem reserva). O cap de escala do SQS fica no event source mapping (scaling_config)."
  type        = number
  default     = -1
}

variable "ingest_timeout_seconds" {
  description = "Timeout da ingestão (regra 6x: visibility da fila = 180s)."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
