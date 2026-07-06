# Rede base do lakehouse: VPC com subnets públicas (EC2 das APIs) e privadas
# (RDS). Sem NAT Gateway por decisão de custo — os serviços privados não saem
# para a internet; Lambdas rodam fora da VPC (falam com S3/SQS por endpoint
# público da AWS).
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

# Subnets públicas: hospedam as EC2 das APIs (fria e quente).
resource "aws_subnet" "public" {
  count = var.az_count

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false # IP público só quando a instância pedir explicitamente

  tags = merge(var.tags, { Name = "${var.prefix}-public-${local.azs[count.index]}" })
}

# Subnets privadas: RDS (e futuros recursos sem exposição à internet).
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

# SG das EC2 de API: HTTPS de entrada, saída liberada (chamadas a S3/SQS/RDS).
resource "aws_security_group" "api" {
  name        = "${var.prefix}-api"
  description = "EC2 das APIs do lakehouse (fria e quente)"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.prefix}-api-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "api_https" {
  for_each = toset(var.api_ingress_cidrs)

  security_group_id = aws_security_group.api.id
  description       = "HTTPS para a API"
  cidr_ipv4         = each.value
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_all" {
  security_group_id = aws_security_group.api.id
  description       = "Saida da API (AWS APIs, RDS)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# SG do RDS: só aceita Postgres vindo do SG da API. Nada de CIDR aberto.
resource "aws_security_group" "database" {
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
