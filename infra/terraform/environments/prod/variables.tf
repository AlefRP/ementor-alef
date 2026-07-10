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
  description = "Porta privada da API de data product (uvicorn na EC2)."
  type        = number
  default     = 8000
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
