variable "prefix" {
  description = "Prefixo de nomes dos recursos."
  type        = string
}

variable "role_arn" {
  description = "Role de execucao dos jobs Glue."
  type        = string
}

variable "raw_bucket" {
  description = "Nome do bucket raw."
  type        = string
}

variable "silver_bucket" {
  description = "Nome do bucket silver/warehouse Iceberg."
  type        = string
}

variable "artifacts_bucket" {
  description = "Nome do bucket de artefatos usado para scripts Glue."
  type        = string
}

variable "cold_job_source" {
  description = "Caminho local do script Glue cold raw -> silver Data Vault."
  type        = string
}

variable "hot_job_source" {
  description = "Caminho local do script Glue hot raw -> silver Data Vault."
  type        = string
}

variable "runtime_source_dir" {
  description = "Diretorio com modulos Python compartilhados dos jobs Glue silver."
  type        = string
}

variable "silver_database_name" {
  description = "Database Glue/Athena da camada silver Data Vault."
  type        = string
  default     = "silver_datavault"
}

variable "cold_datasets" {
  description = "Datasets raw frios processados pelo job batch; use all para todos."
  type        = string
  default     = "all"
}

variable "cold_schedule_expression" {
  description = "Agenda EventBridge do job Glue batch cold -> silver."
  type        = string
  default     = "rate(2 hours)"
}

variable "hot_schedule_expression" {
  description = "Agenda EventBridge do job Glue microbatch hot -> silver."
  type        = string
  default     = "rate(15 minutes)"
}

variable "glue_version" {
  description = "Versao do AWS Glue usada pelos jobs Spark/Iceberg."
  type        = string
  default     = "5.0"
}

variable "worker_type" {
  description = "Tipo de worker Glue."
  type        = string
  default     = "G.1X"
}

variable "number_of_workers" {
  description = "Quantidade de workers por job Glue."
  type        = number
  default     = 2
}

variable "alert_email" {
  description = "E-mail (opcional) que assina o topico SNS de falhas dos jobs Glue."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags adicionais."
  type        = map(string)
  default     = {}
}

