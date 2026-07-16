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

variable "silver_database_name" {
  description = "Database Glue/Athena da camada silver (alvo dos grants de leitura do consumo)."
  type        = string
}

variable "gold_database_name" {
  description = "Database Glue/Athena da camada gold (alvo dos grants de leitura do consumo)."
  type        = string
}

variable "consumer_principal_arns" {
  description = "ARNs IAM (users/roles) com leitura na silver e na gold via Lake Formation. Vazio = quem aplica (o admin do data lake). O analista entra sempre, além desta lista."
  type        = list(string)
  default     = []
}

variable "gold_workgroup_name" {
  description = "Workgroup do Athena da gold (escopo das queries do analista)."
  type        = string
}

variable "analistas" {
  description = "Nomes dos analistas humanos; cada um vira o user IAM <prefixo>-analista-<nome>, com consumo via Lake Formation."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
