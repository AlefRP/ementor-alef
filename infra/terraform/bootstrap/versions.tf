# Bootstrap usa state LOCAL de propósito: ele cria o bucket que os ambientes
# usam como backend remoto (problema do ovo e da galinha). Apply único e manual.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
