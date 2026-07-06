terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # State remoto no bucket dedicado criado por infra/terraform/bootstrap
  # (apply único, manual). Lock nativo do S3 (>= 1.10), sem DynamoDB.
  backend "s3" {
    bucket       = "ementor-alef-lakehouse-tf-state"
    key          = "lakehouse/prod/terraform.tfstate"
    region       = "sa-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
