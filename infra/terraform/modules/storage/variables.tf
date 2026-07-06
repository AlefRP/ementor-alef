variable "prefix" {
  description = "Prefixo de nomes dos buckets (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "layers" {
  description = "Camadas do lakehouse que ganham bucket próprio."
  type        = set(string)
  default     = ["raw", "silver"]
}

variable "force_destroy" {
  description = "Permite destruir buckets COM dados (use só em teardown do lab)."
  type        = bool
  default     = false
}

variable "noncurrent_version_expiration_days" {
  description = "Dias até expirar versões antigas dos objetos (higiene de custo)."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags adicionais aplicadas aos buckets."
  type        = map(string)
  default     = {}
}
