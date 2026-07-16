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
  api_db_user           = var.api_db_user # mesmo usuário do PGUSER da API fria

  # Grants de leitura do consumo: referenciar os OUTPUTS dos módulos cria a
  # aresta grant→database no grafo (grant em database inexistente falha).
  silver_database_name = module.silver_datavault.silver_database_name
  gold_database_name   = module.gold.gold_database_name
  gold_workgroup_name  = module.gold.workgroup_name
  analistas            = var.analistas

  tags = local.tags
}

# =====================================================================
# ARQUITETURA — o lakehouse propriamente dito.
# Camada fria começa no RDS; camada quente começa na Event API (EC2).
# =====================================================================

# ---- Camada fria: API privada (EC2) + Lambda de ingestão agendada ----
module "api_cold" {
  source = "../../modules/api_ec2"

  prefix                = local.prefix
  service_name          = "api-cold"
  service_description   = "API de data product Olist (camada fria)"
  app_module            = "src.cold.api_orders.main:app"
  subnet_id             = module.network.private_subnet_ids[0]
  private_ip            = cidrhost(module.network.private_subnet_cidrs[0], 20) # fixo p/ SAN do cert
  security_group_id     = module.network.api_security_group_id
  instance_profile_name = module.governance.ec2_api_instance_profile_name
  api_port              = var.api_port
  artifacts_bucket      = module.storage.bucket_ids["artifacts"]
  validate_bundle       = var.validate_bundle

  # Sem senha: DB_AUTH=iam faz a API assinar um token de 15 min com a role.
  service_env = {
    DB_AUTH            = "iam"
    PGHOST             = module.database.address
    PGPORT             = tostring(module.database.port)
    PGDATABASE         = module.database.db_name
    PGUSER             = var.api_db_user
    AWS_DEFAULT_REGION = data.aws_region.current.name
  }

  tags = local.tags
}

module "ingestion_cold" {
  source = "../../modules/lambda_ingest"

  prefix              = local.prefix
  handler_source      = "${path.module}/../../../../src/cold/lambda_ingest/handler.py"
  role_arn            = module.governance.lambda_ingest_cold_role_arn
  subnet_ids          = module.network.private_subnet_ids
  security_group_id   = module.network.lambda_ingest_security_group_id
  raw_bucket          = module.storage.bucket_ids["raw"]
  api_base_url        = module.api_cold.base_url # HTTPS pelo IP privado fixo
  api_ca_pem          = module.api_cold.ca_pem
  schedule_expression = var.ingest_schedule
  extra_datasets      = var.cold_extra_datasets
  tags                = local.tags
}

# ---- Camada quente: Event API (EC2) -> SQS -> Lambda consumidora -> raw ----
# A Event API é a fronteira de entrada: valida o contrato do evento e publica na
# fila (role ec2-api, via interface endpoint do SQS — a subnet é privada e sem
# NAT). Quem CHAMA a API é simulação (adiante).
module "api_events" {
  source = "../../modules/api_ec2"

  prefix                = local.prefix
  service_name          = "api-events"
  service_description   = "Event API de pedidos (camada quente)"
  app_module            = "src.hot.api_events.main:app"
  subnet_id             = module.network.private_subnet_ids[0]
  private_ip            = cidrhost(module.network.private_subnet_cidrs[0], 21) # fixo p/ SAN do cert
  security_group_id     = module.network.api_security_group_id
  instance_profile_name = module.governance.ec2_api_instance_profile_name
  api_port              = var.api_port
  artifacts_bucket      = module.storage.bucket_ids["artifacts"]
  validate_bundle       = var.validate_bundle

  # Mesmo bundle da API fria (é o mesmo pacote Python); muda só o app servido.
  service_env = {
    QUEUE_URL          = module.messaging.events_queue_url
    AWS_DEFAULT_REGION = data.aws_region.current.name
  }

  tags = local.tags
}

module "ingestion_hot" {
  source = "../../modules/hot_ingestion"

  prefix          = local.prefix
  ingest_source   = "${path.module}/../../../../src/hot/lambda_raw_ingest/handler.py"
  ingest_role_arn = module.governance.lambda_ingest_hot_role_arn

  events_queue_arn  = module.messaging.events_queue_arn
  subnet_ids        = module.network.private_subnet_ids
  security_group_id = module.network.lambda_hot_security_group_id
  raw_bucket        = module.storage.bucket_ids["raw"]

  tags = local.tags
}

# ---- Camada silver: Glue Spark -> Iceberg Raw Data Vault ----
module "silver_datavault" {
  source = "../../modules/glue_silver"

  prefix           = local.prefix
  role_arn         = module.governance.glue_job_role_arn
  raw_bucket       = module.storage.bucket_ids["raw"]
  silver_bucket    = module.storage.bucket_ids["silver"]
  artifacts_bucket = module.storage.bucket_ids["artifacts"]

  cold_job_source    = "${path.module}/../../../../src/cold/glue_silver/job.py"
  hot_job_source     = "${path.module}/../../../../src/hot/glue_silver_microbatch/job.py"
  runtime_source_dir = "${path.module}/../../../../src/glue_silver_runtime"

  silver_database_name     = var.silver_database_name
  cold_datasets            = var.silver_cold_datasets
  cold_schedule_expression = var.silver_cold_schedule
  hot_schedule_expression  = var.silver_hot_schedule
  glue_version             = var.glue_version
  worker_type              = var.glue_worker_type
  number_of_workers        = var.glue_number_of_workers
  alert_email              = var.silver_alert_email
  tags                     = local.tags
}

# ---- Camada gold + consumer: views do Athena sobre a silver ----
# Fecha as duas camadas: o DDL das views vive em src/{cold,hot}/athena_gold e é
# aplicado por `make athena-gold` (a esteira roda no merge, após o apply).
module "gold" {
  source = "../../modules/athena_gold"

  prefix             = local.prefix
  gold_database_name = var.gold_database_name
  artifacts_bucket   = module.storage.bucket_ids["artifacts"]
  force_destroy      = var.force_destroy # teardown do lab: apaga o histórico de queries
  tags               = local.tags
}

# ---- Governança: alarmes do CloudWatch ----
# Log group todo componente já tinha; o que faltava era alguém OLHAR. Sem estes
# alarmes, ingestão parada só aparece quando o dado velho incomoda no Athena.
module "observability" {
  source = "../../modules/observability"

  prefix = local.prefix

  lambda_function_names = {
    "ingest-cold"    = module.ingestion_cold.function_name
    "ingest-hot"     = module.ingestion_hot.ingest_function_name
    "event-producer" = module.sim_event_producer.function_name
  }

  api_instance_ids = {
    "api-cold"   = module.api_cold.instance_id
    "api-events" = module.api_events.instance_id
  }

  events_queue_name       = module.messaging.events_queue_name
  events_dlq_name         = module.messaging.events_dlq_name
  max_message_age_seconds = var.max_message_age_seconds
  alert_email             = var.silver_alert_email # mesmo destino dos alertas do Glue
  tags                    = local.tags
}

# =====================================================================
# SIMULAÇÃO — fora da arquitetura. Só alimenta as fronteiras de entrada
# (Event API e RDS) para o lab ter dados. Num cenário real, quem faz isso
# são os sistemas de origem. Remova este bloco inteiro sem afetar o lakehouse.
# =====================================================================

# Simula o sistema de origem que emite eventos: chama a Event API (não o SQS).
module "sim_event_producer" {
  source = "../../modules/simulation/event_producer"

  prefix    = local.prefix
  build_dir = "${path.module}/../../../../build/event-producer"

  api_base_url      = module.api_events.base_url # HTTPS pelo IP privado fixo
  api_ca_pem        = module.api_events.ca_pem
  subnet_ids        = module.network.private_subnet_ids
  security_group_id = module.network.lambda_event_producer_security_group_id

  schedule_expression = var.hot_schedule
  events_per_run      = var.hot_events_per_run
  tags                = local.tags
}

# Senha do master do RDS (secret gerenciado). Lida aqui, no apply, e injetada
# como env var da Lambda de seed — a única forma de semear o banco privado sem
# um interface endpoint pago de Secrets Manager. O state já é cifrado no S3.
data "aws_secretsmanager_secret_version" "rds_master" {
  secret_id = module.database.master_user_secret_arn
}

# Simula o sistema transacional: cria o schema, popula o Olist e o api_reader.
module "sim_db_seeder" {
  source = "../../modules/simulation/db_seeder"

  prefix            = local.prefix
  build_dir         = "${path.module}/../../../../build/db-seeder"
  subnet_ids        = module.network.private_subnet_ids
  security_group_id = module.network.lambda_db_seeder_security_group_id

  pghost     = module.database.address
  pgport     = module.database.port
  pgdatabase = module.database.db_name
  pguser     = module.database.master_username
  pgpassword = jsondecode(data.aws_secretsmanager_secret_version.rds_master.secret_string)["password"]

  tags = local.tags
}


