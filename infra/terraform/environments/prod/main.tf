# Composição do ambiente prod do lakehouse: rede, armazenamento, mensageria,
# banco de origem (Olist), governança e camada fria (API privada + Lambda de
# ingestão). O plan continua validando a integração com a conta via STS.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

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

  prefix   = local.prefix
  vpc_cidr = var.vpc_cidr
  api_port = var.api_port
  tags     = local.tags
}

module "storage" {
  source = "../../modules/storage"

  prefix        = local.prefix
  layers        = ["raw", "silver", "artifacts"] # artifacts: bundles de deploy
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
  artifacts_bucket_arn  = module.storage.bucket_arns["artifacts"]
  events_queue_arn      = module.messaging.events_queue_arn
  rds_master_secret_arn = module.database.master_user_secret_arn
  rds_resource_id       = module.database.resource_id
  tags                  = local.tags
}

# ---- Camada fria: API privada (EC2) + Lambda de ingestão agendada ----
module "api_cold" {
  source = "../../modules/api_ec2"

  prefix                = local.prefix
  subnet_id             = module.network.private_subnet_ids[0]
  security_group_id     = module.network.api_security_group_id
  instance_profile_name = module.governance.ec2_api_instance_profile_name
  api_port              = var.api_port
  artifacts_bucket      = module.storage.bucket_ids["artifacts"]
  pghost                = module.database.address
  pgport                = module.database.port
  pgdatabase            = module.database.db_name
  aws_region            = data.aws_region.current.name
  tags                  = local.tags
}

module "ingestion_cold" {
  source = "../../modules/lambda_ingest"

  prefix              = local.prefix
  handler_source      = "${path.module}/../../../../src/cold/lambda_ingest/handler.py"
  role_arn            = module.governance.lambda_ingest_cold_role_arn
  subnet_ids          = module.network.private_subnet_ids
  security_group_id   = module.network.lambda_ingest_security_group_id
  raw_bucket          = module.storage.bucket_ids["raw"]
  api_base_url        = "http://${module.api_cold.private_dns}:${var.api_port}"
  schedule_expression = var.ingest_schedule
  tags                = local.tags
}
