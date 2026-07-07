variable "prefix" {
  description = "Prefixo de nomes dos recursos (ex.: ementor-lakehouse-prod)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR da VPC do lakehouse."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr deve ser um bloco CIDR válido."
  }
}

variable "az_count" {
  description = "Quantidade de AZs (subnets públicas/privadas por AZ)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count deve ser 2 ou 3 (RDS exige subnet group em >= 2 AZs)."
  }
}

variable "api_ingress_cidrs" {
  description = "CIDRs autorizados a acessar a API na EC2 (porta 443)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos do módulo."
  type        = map(string)
  default     = {}
}
