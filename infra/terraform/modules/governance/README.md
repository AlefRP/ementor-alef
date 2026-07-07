# Módulo governance

Implementa a story de governança do datalake:

1. **Lake Formation**: buckets raw e silver registrados como *Data Lake
   Locations* (`aws_lakeformation_resource`) via role de serviço dedicada;
   Glue recebe `DATA_LOCATION_ACCESS` nos dois locations.
2. **Roles de execução least-privilege** (uma por serviço/função):

| Role | Pode | Não pode |
|---|---|---|
| `lambda-ingest-cold` | `s3:PutObject` em `raw/*`; logs | ler raw/silver, tocar SQS |
| `lambda-ingest-hot` | idem + consumir a fila `events` | publicar na fila, ler silver |
| `glue-silver` | ler `raw`, ler/escrever/compactar `silver`; catálogo/logs (managed do serviço) | tocar SQS, IAM, outros buckets |
| `ec2-api` | `sqs:SendMessage` na `events`; ler o secret do RDS | qualquer acesso a raw/silver |

Sem `Action:"*"`/`Resource:"*"` em nenhuma policy própria; assume-role restrito
ao serviço correspondente.
