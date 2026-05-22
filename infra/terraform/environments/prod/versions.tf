terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend remoto recomendado para state compartilhado (descomente e ajuste):
  # backend "s3" {
  #   bucket = "<seu-bucket-de-state>"
  #   key    = "lakehouse/prod/terraform.tfstate"
  #   region = "<sua-regiao>"
  # }
}
