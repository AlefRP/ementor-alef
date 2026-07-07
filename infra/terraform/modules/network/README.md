# Módulo network

VPC do lakehouse com `az_count` subnets públicas (EC2 das APIs) e privadas (RDS),
IGW e rotas. **Sem NAT Gateway** (decisão de custo — nada privado precisa sair
para a internet; Lambdas rodam fora da VPC).

Segurança:
- SG default da VPC travado sem regras.
- `api`: ingress 443 dos CIDRs de `api_ingress_cidrs`; egress liberado.
- `database`: ingress 5432 **somente** a partir do SG `api`; egress bloqueado.
