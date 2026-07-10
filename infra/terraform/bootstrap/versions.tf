# Bootstrap usa state LOCAL de propósito: ele cria o bucket que os ambientes
# usam como backend remoto (problema do ovo e da galinha). Apply único e manual.
terraform {
  # Piso = versão do terraform do desenvolvimento local (state gravado por um
  # CLI mais novo não pode ser lido por CLIs mais antigos).
  required_version = ">= 1.15.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
