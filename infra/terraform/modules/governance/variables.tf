variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "raw_bucket_arn" {
  description = "ARN do bucket da camada raw."
  type        = string
}

variable "silver_bucket_arn" {
  description = "ARN do bucket da camada silver."
  type        = string
}

variable "events_queue_arn" {
  description = "ARN da fila SQS de eventos (camada quente)."
  type        = string
}

variable "rds_master_secret_arn" {
  description = "ARN do secret com a senha master do RDS (usado só pelo seed)."
  type        = string
}

variable "rds_resource_id" {
  description = "Resource id (dbi-*) do RDS para o ARN de rds-db:connect."
  type        = string
}

variable "api_db_user" {
  description = "Usuário do banco (com grant rds_iam) usado pela API."
  type        = string
  default     = "api_reader"
}

variable "artifacts_bucket_arn" {
  description = "ARN do bucket de artefatos de deploy (bundle da API)."
  type        = string
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
