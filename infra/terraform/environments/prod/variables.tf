variable "project" {
  description = "Nome curto do projeto (prefixo de recursos e buckets)."
  type        = string
  default     = "ementor-lakehouse"
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

variable "api_ingress_cidrs" {
  description = "CIDRs com acesso HTTPS às APIs em EC2."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "force_destroy" {
  description = "Teardown: permite destruir buckets raw/silver mesmo com dados."
  type        = bool
  default     = false
}
