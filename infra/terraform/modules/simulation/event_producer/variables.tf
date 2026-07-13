variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: alef-rp-aws-lakehouse-prod)."
  type        = string
}

variable "build_dir" {
  description = "Diretório do producer empacotado (simulation/ + Faker); ver make event-producer-bundle."
  type        = string
}

variable "api_base_url" {
  description = "URL HTTPS da Event API (IP privado fixo da EC2) — destino da simulação."
  type        = string
}

variable "api_ca_pem" {
  description = "CA self-signed da Event API, usada pelo produtor para validar o TLS (certificado público, não é segredo)."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets PRIVADAS da Lambda (a Event API só é alcançável de dentro da VPC)."
  type        = list(string)
}

variable "security_group_id" {
  description = "SG do produtor (egress só para a Event API; ver módulo network)."
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

variable "events_per_request" {
  description = "Eventos por requisição à Event API (o produtor pagina acima disso; teto da API: 500)."
  type        = number
  default     = 100
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
