variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: alef-rp-aws-lakehouse-prod)."
  type        = string
}

variable "build_dir" {
  description = "Diretório do producer empacotado (simulation/ + Faker); ver make event-producer-bundle."
  type        = string
}

variable "events_queue_url" {
  description = "URL da fila de eventos (destino da simulação)."
  type        = string
}

variable "events_queue_arn" {
  description = "ARN da fila de eventos (escopo da policy de SendMessage)."
  type        = string
}

variable "schedule_expression" {
  description = "Cadência do producer (rate/cron do EventBridge)."
  type        = string
  default     = "rate(1 minute)"
}

variable "events_per_run" {
  description = "Eventos gerados por execução."
  type        = number
  default     = 60
}

variable "reserved_concurrency" {
  description = "Concorrência reservada (-1 = sem reserva). Padrão -1: free tier limita a concorrência total a 10 e a AWS exige pool não-reservado >= 10."
  type        = number
  default     = -1
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
