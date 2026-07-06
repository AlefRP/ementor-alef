# RDS PostgreSQL que serve de sistema de origem do lakehouse (dataset Olist —
# e-commerce brasileiro, carga única via scripts/database/). Privado, cifrado
# e com senha gerenciada pela AWS (Secrets Manager) — nenhum segredo no código
# nem no state.
resource "aws_db_subnet_group" "this" {
  name       = "${var.prefix}-db"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.prefix}-db-subnets" })
}

resource "aws_db_instance" "this" {
  identifier     = "${var.prefix}-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.master_username
  # Senha criada e rotacionável no Secrets Manager pela própria AWS:
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false

  backup_retention_period    = var.backup_retention_days
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true

  # Decisões de custo da mentoria (documentadas — reveja para produção real):
  # checkov:skip=CKV_AWS_157: single-AZ por custo; dataset de exemplo recarregável
  multi_az = false
  # checkov:skip=CKV_AWS_293: sem deletion protection para permitir teardown do lab
  deletion_protection = false
  skip_final_snapshot = true

  tags = merge(var.tags, { Name = "${var.prefix}-postgres" })
}
