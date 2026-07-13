variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: alef-rp-aws-lakehouse-prod)."
  type        = string
}

variable "lambda_function_names" {
  description = "Lambdas vigiadas por alarme de erro — mapa rótulo => nome da função."
  type        = map(string)
  default     = {}
}

variable "api_instance_ids" {
  description = "EC2 das APIs vigiadas por status check — mapa rótulo => instance id."
  type        = map(string)
  default     = {}
}

variable "events_queue_name" {
  description = "Nome da fila de eventos (dimensão do alarme de backlog)."
  type        = string
}

variable "events_dlq_name" {
  description = "Nome da DLQ (dimensão do alarme de mensagem não processada)."
  type        = string
}

variable "max_message_age_seconds" {
  description = "Idade máxima tolerada da mensagem mais antiga na fila antes do alarme."
  type        = number
  default     = 900 # 15 min: com producer a cada minuto, sinaliza consumo parado
}

variable "alert_email" {
  description = "E-mail que recebe os alarmes (vazio desliga a inscrição; confirme o e-mail da AWS)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
