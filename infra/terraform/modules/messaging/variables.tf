variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "Visibility timeout da fila (regra prática: 6x o timeout da Lambda consumidora)."
  type        = number
  default     = 180
}

variable "max_receive_count" {
  description = "Tentativas de consumo antes da mensagem ir para a DLQ."
  type        = number
  default     = 4
}

variable "tags" {
  description = "Tags adicionais aplicadas às filas."
  type        = map(string)
  default     = {}
}
