variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: alef-rp-aws-lakehouse-prod)."
  type        = string
}

variable "gold_database_name" {
  description = "Database Glue/Athena da camada gold (views dimensionais)."
  type        = string
}

variable "artifacts_bucket" {
  description = "Bucket onde o Athena grava o resultado das queries (prefixo athena-results/)."
  type        = string
}

variable "bytes_scanned_cutoff" {
  description = "Teto de bytes escaneados por query (freio de custo). Mínimo aceito pela AWS: 10 MB."
  type        = number
  default     = 1073741824 # 1 GiB — folgado para o Olist, barato se alguém errar
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
