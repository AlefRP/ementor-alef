variable "project" {
  description = "Nome curto do projeto (prefixo de recursos e buckets)."
  type        = string
  default     = "alef-rp-aws-lakehouse"
}

variable "environment" {
  description = "Nome do ambiente."
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR da VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "api_port" {
  description = "Porta privada das APIs (uvicorn na EC2) — fria e quente."
  type        = number
  default     = 8000
}

# Uma variável só: o PGUSER da API fria e o dbuser do rds-db:connect na policy
# IAM (governance) PRECISAM ser o mesmo — separados, divergiriam em silêncio e a
# API tomaria 'PAM authentication failed' só em runtime.
variable "api_db_user" {
  description = "Usuário do banco usado pela API fria (com grant rds_iam, sem senha)."
  type        = string
  default     = "api_reader"
}

variable "ingest_schedule" {
  description = "Agenda (EventBridge) da Lambda de ingestão fria. Horária no lab: regras rate() só disparam depois de um intervalo completo, e 1 dia deixava o pipeline inobservável."
  type        = string
  default     = "rate(1 hour)"
}

variable "cold_extra_datasets" {
  description = "Datasets do Olist além de orders servidos pela API (/v1/<nome>) e ingeridos com cursor por PK (snapshot resumível)."
  type        = list(string)
  default = [
    "customers",
    "sellers",
    "products",
    "geolocation",
    "product_category_name_translation",
    "order_items",
    "order_payments",
    "order_reviews",
  ]
}

variable "hot_schedule" {
  description = "Cadência do producer de eventos da camada quente."
  type        = string
  default     = "rate(1 minute)"
}

variable "hot_events_per_run" {
  description = "Eventos sintéticos gerados por execução do producer."
  type        = number
  default     = 60
}

variable "force_destroy" {
  description = "Teardown: permite destruir buckets raw/silver mesmo com dados."
  type        = bool
  default     = false
}

variable "validate_bundle" {
  description = "Valida o bundle da API no plan/apply. Os alvos de destroy passam false: o refresh lê data sources e um bundle ausente travaria o teardown."
  type        = bool
  default     = true
}

variable "silver_database_name" {
  description = "Database Glue/Athena da camada silver Data Vault."
  type        = string
  default     = "silver_datavault"
}

variable "gold_database_name" {
  description = "Database Glue/Athena da camada gold (views dimensionais sobre a silver)."
  type        = string
  default     = "gold"
}

variable "max_message_age_seconds" {
  description = "Idade máxima tolerada da mensagem mais antiga na fila de eventos antes do alarme."
  type        = number
  default     = 900
}

variable "silver_cold_datasets" {
  description = "Datasets raw frios processados pelo job Glue silver; use all para todos."
  type        = string
  default     = "all"
}

variable "silver_cold_schedule" {
  description = "Agenda do job Glue batch cold raw -> silver."
  type        = string
  default     = "rate(2 hours)"
}

variable "silver_hot_schedule" {
  description = "Agenda do job Glue microbatch hot raw -> silver."
  type        = string
  default     = "rate(15 minutes)"
}

variable "glue_version" {
  description = "Versao do AWS Glue para jobs Spark/Iceberg."
  type        = string
  default     = "5.0"
}

variable "glue_worker_type" {
  description = "Tipo de worker Glue para a camada silver."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Numero de workers dos jobs Glue silver."
  type        = number
  default     = 2
}

variable "silver_alert_email" {
  description = "E-mail (opcional) que assina o topico SNS de falhas dos jobs Glue silver."
  type        = string
  default     = ""
}
