variable "state_bucket_name" {
  description = "Nome do bucket S3 dedicado ao state remoto do Terraform (globalmente único)."
  type        = string
  default     = "ementor-alef-lakehouse-tf-state"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Nome de bucket S3 inválido."
  }
}
