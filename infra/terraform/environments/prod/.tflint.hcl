plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Regras específicas da AWS (opcional). Requer `tflint --init` para baixar o
# plugin antes de rodar o lint:
# plugin "aws" {
#   enabled = true
#   version = "0.31.0"
#   source  = "github.com/terraform-linters/tflint-ruleset-aws"
# }
