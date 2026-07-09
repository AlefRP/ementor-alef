# Rede base do lakehouse — postura 100% privada para os workloads: EC2 das
# APIs, Lambdas e RDS ficam nas subnets privadas, sem IP público e sem NAT.
# O S3 (dados, artefatos de deploy e repositórios do Amazon Linux) é alcançado
# pelo gateway endpoint (gratuito); o RDS autentica por token IAM assinado
# localmente. As subnets públicas ficam reservadas para recursos de borda
# eventuais (ex.: bastion temporário) — nenhum workload roda nelas.
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.prefix}-vpc" })
}

# Subnets públicas: reservadas (borda); sem workloads por decisão de postura.
resource "aws_subnet" "public" {
  count = var.az_count

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false # IP público só quando a instância pedir explicitamente

  tags = merge(var.tags, { Name = "${var.prefix}-public-${local.azs[count.index]}" })
}

# Subnets privadas: RDS, EC2 das APIs e Lambdas (nada exposto à internet).
resource "aws_subnet" "private" {
  count = var.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)
  availability_zone = local.azs[count.index]

  tags = merge(var.tags, { Name = "${var.prefix}-private-${local.azs[count.index]}" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-igw" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(var.tags, { Name = "${var.prefix}-public-rt" })
}

resource "aws_route_table_association" "public" {
  count = var.az_count

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Rota privada sem saída para internet (sem NAT): tráfego fica na VPC.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-private-rt" })
}

resource "aws_route_table_association" "private" {
  count = var.az_count

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Trava o SG default da VPC sem nenhuma regra (baseline de segurança —
# ninguém deve usar o SG default).
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-default-sg-locked" })
}

# SG das EC2 de API (privadas): entrada só da Lambda (regra adiante); saída
# restrita ao S3 (gateway endpoint: dados, artefatos, repos AL2023) e ao RDS.
resource "aws_security_group" "api" {
  #checkov:skip=CKV2_AWS_5: falso positivo - o SG e anexado em outro modulo (EC2/Lambda/RDS); o grafo do checkov nao cruza modulos
  name        = "${var.prefix}-api"
  description = "EC2 das APIs do lakehouse (fria e quente)"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-api-sg" })
}

resource "aws_vpc_security_group_egress_rule" "api_to_s3" {
  security_group_id = aws_security_group.api.id
  description       = "HTTPS ao S3 via gateway endpoint (dados/artefatos/repos)"
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_to_database" {
  security_group_id            = aws_security_group.api.id
  description                  = "PostgreSQL no RDS"
  referenced_security_group_id = aws_security_group.database.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

# Gateway endpoint de S3 (sem custo): a Lambda de ingestão roda nas subnets
# privadas (sem NAT) e alcança o S3 por aqui; nas públicas, mantém o tráfego
# EC2 -> S3 no backbone da AWS.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.public.id]

  tags = merge(var.tags, { Name = "${var.prefix}-s3-endpoint" })
}

data "aws_region" "current" {}

# SG da Lambda de ingestão fria: só sai para a API (porta privada) e para o
# S3 via gateway endpoint. Nenhuma entrada.
resource "aws_security_group" "lambda_ingest" {
  #checkov:skip=CKV2_AWS_5: falso positivo - o SG e anexado em outro modulo (EC2/Lambda/RDS); o grafo do checkov nao cruza modulos
  name        = "${var.prefix}-lambda-ingest"
  description = "Lambda de ingestao fria (VPC) - chama a API e escreve no S3"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-lambda-ingest-sg" })
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_api" {
  security_group_id            = aws_security_group.lambda_ingest.id
  description                  = "Chamada privada a API de data product"
  referenced_security_group_id = aws_security_group.api.id
  from_port                    = var.api_port
  to_port                      = var.api_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_s3" {
  security_group_id = aws_security_group.lambda_ingest.id
  description       = "HTTPS ao S3 via gateway endpoint"
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# SG da Lambda de ingestão quente (SQS -> raw): o polling do SQS é feito pelo
# serviço Lambda (fora da VPC); a função só precisa alcançar o S3.
resource "aws_security_group" "lambda_hot" {
  #checkov:skip=CKV2_AWS_5: falso positivo - o SG e anexado em outro modulo (EC2/Lambda/RDS); o grafo do checkov nao cruza modulos
  name        = "${var.prefix}-lambda-hot"
  description = "Lambda de ingestao quente (VPC) - escreve no S3"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-lambda-hot-sg" })
}

resource "aws_vpc_security_group_egress_rule" "lambda_hot_to_s3" {
  security_group_id = aws_security_group.lambda_hot.id
  description       = "HTTPS ao S3 via gateway endpoint"
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# SG da Lambda de bootstrap do banco: roda na VPC só para alcançar o RDS
# (o RDS é privado e a EC2 não chega ao Secrets Manager). Sem entrada.
resource "aws_security_group" "lambda_bootstrap" {
  #checkov:skip=CKV2_AWS_5: falso positivo - o SG e anexado em outro modulo (bootstrap_db); o grafo do checkov nao cruza modulos
  name        = "${var.prefix}-lambda-bootstrap"
  description = "Lambda de bootstrap do banco (VPC) - conecta no RDS"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-lambda-bootstrap-sg" })
}

resource "aws_vpc_security_group_egress_rule" "lambda_bootstrap_to_database" {
  security_group_id            = aws_security_group.lambda_bootstrap.id
  description                  = "PostgreSQL no RDS (schema, seed e api_reader)"
  referenced_security_group_id = aws_security_group.database.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_bootstrap" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL a partir da Lambda de bootstrap"
  referenced_security_group_id = aws_security_group.lambda_bootstrap.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

# A API só aceita a porta privada vinda do SG da Lambda (tráfego intra-VPC).
resource "aws_vpc_security_group_ingress_rule" "api_from_lambda" {
  security_group_id            = aws_security_group.api.id
  description                  = "API de data product a partir da Lambda de ingestao"
  referenced_security_group_id = aws_security_group.lambda_ingest.id
  from_port                    = var.api_port
  to_port                      = var.api_port
  ip_protocol                  = "tcp"
}

# SG do RDS: só aceita Postgres vindo do SG da API. Nada de CIDR aberto.
resource "aws_security_group" "database" {
  #checkov:skip=CKV2_AWS_5: falso positivo - o SG e anexado em outro modulo (EC2/Lambda/RDS); o grafo do checkov nao cruza modulos
  name        = "${var.prefix}-database"
  description = "RDS PostgreSQL do lakehouse"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-database-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "database_from_api" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL a partir da API"
  referenced_security_group_id = aws_security_group.api.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "database_none" {
  security_group_id = aws_security_group.database.id
  description       = "RDS nao inicia conexoes de saida"
  cidr_ipv4         = "127.0.0.1/32" # egress efetivamente bloqueado
  ip_protocol       = "-1"
}
