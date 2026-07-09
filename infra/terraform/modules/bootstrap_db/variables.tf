variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: alef-rp-aws-lakehouse-prod)."
  type        = string
}

variable "build_dir" {
  description = "Diretório do pacote da Lambda (handler + psycopg + faker + .sql); ver make bootstrap-db-bundle."
  type        = string
}

variable "role_arn" {
  description = "Role de execução (lambda-bootstrap-db, módulo governance)."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets privadas onde a Lambda roda (mesma VPC do RDS)."
  type        = list(string)
}

variable "security_group_id" {
  description = "SG da Lambda de bootstrap (egress só para o RDS; módulo network)."
  type        = string
}

variable "pghost" {
  description = "Endpoint (host) do RDS PostgreSQL."
  type        = string
}

variable "pgport" {
  description = "Porta do RDS PostgreSQL."
  type        = number
  default     = 5432
}

variable "pgdatabase" {
  description = "Database do Olist no RDS."
  type        = string
  default     = "olist"
}

variable "pguser" {
  description = "Usuário master do RDS (único que pode criar schema e o api_reader)."
  type        = string
}

variable "pgpassword" {
  description = "Senha do master, lida do secret gerenciado do RDS pelo Terraform."
  type        = string
  sensitive   = true
}

variable "seed_orders" {
  description = "Quantidade de pedidos sintéticos gerados no seed."
  type        = number
  default     = 5000
}

variable "seed_customers" {
  description = "Quantidade de clientes sintéticos gerados no seed."
  type        = number
  default     = 2000
}

variable "timeout_seconds" {
  description = "Timeout: o seed carrega dezenas de milhares de linhas via COPY."
  type        = number
  default     = 600
}

variable "memory_mb" {
  description = "Memória da função (o dataset é montado em memória antes do COPY)."
  type        = number
  default     = 1024
}

variable "reserved_concurrency" {
  description = "Concorrência reservada (-1 = sem reserva; free tier exige pool não-reservado >= 10)."
  type        = number
  default     = -1
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
