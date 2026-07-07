# Composição do ambiente prod do lakehouse: rede, armazenamento, mensageria,
# banco de origem (Olist) e governança. O plan continua validando a integração
# com a conta via STS (aws_caller_identity).
data "aws_caller_identity" "current" {}

locals {
  prefix = "${var.project}-${var.environment}"

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "network" {
  source = "../../modules/network"

  prefix            = local.prefix
  vpc_cidr          = var.vpc_cidr
  api_ingress_cidrs = var.api_ingress_cidrs
  tags              = local.tags
}

module "storage" {
  source = "../../modules/storage"

  prefix        = local.prefix
  force_destroy = var.force_destroy
  tags          = local.tags
}

module "messaging" {
  source = "../../modules/messaging"

  prefix = local.prefix
  tags   = local.tags
}

module "database" {
  source = "../../modules/database"

  prefix             = local.prefix
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.database_security_group_id
  tags               = local.tags
}

module "governance" {
  source = "../../modules/governance"

  prefix                = local.prefix
  raw_bucket_arn        = module.storage.bucket_arns["raw"]
  silver_bucket_arn     = module.storage.bucket_arns["silver"]
  events_queue_arn      = module.messaging.events_queue_arn
  rds_master_secret_arn = module.database.master_user_secret_arn
  tags                  = local.tags
}
