# Região e credenciais vêm das variáveis de ambiente lidas nativamente pelo
# provider AWS: AWS_DEFAULT_REGION / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# (definidas no job terraform do CI e no rollback).
provider "aws" {}
