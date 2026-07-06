# Região e credenciais via variáveis de ambiente (AWS_DEFAULT_REGION,
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY), como no restante do repo.
provider "aws" {
  default_tags {
    tags = {
      Project   = "aws-lakehouse-mentoria"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
