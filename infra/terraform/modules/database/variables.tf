variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "private_subnet_ids" {
  description = "Subnets privadas onde o RDS vive (>= 2 AZs)."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "O subnet group do RDS exige subnets em pelo menos 2 AZs."
  }
}

variable "security_group_id" {
  description = "SG do banco (ingress 5432 restrito ao SG da API)."
  type        = string
}

variable "engine_version" {
  description = "Versão maior do PostgreSQL."
  type        = string
  default     = "16"
}

variable "instance_class" {
  description = "Classe da instância (t4g.micro cobre o dataset Olist ~1,5 GB)."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Storage inicial em GB."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Nome do database inicial (recebe o dataset Olist)."
  type        = string
  default     = "olist"
}

variable "backup_retention_days" {
  description = "Dias de retenção de backup automatizado (free tier: máximo 1)."
  type        = number
  default     = 1
}

variable "master_username" {
  description = "Usuário master (senha gerenciada pela AWS no Secrets Manager)."
  type        = string
  default     = "lakehouse_admin"
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
