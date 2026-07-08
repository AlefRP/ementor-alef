# hot_ingestion — camada quente (producer → SQS → Lambda → raw)

Dois componentes:

1. **Producer** (`src/hot/event_producer`): agendado pelo EventBridge
   (padrão: a cada minuto), gera eventos sintéticos coerentes com o domínio
   Olist (stdlib, sem dependências) e publica na fila em lotes de 10. Roda
   **fora da VPC** de propósito: o SQS não tem gateway endpoint gratuito e,
   de fora, é alcançado pelo endpoint público com TLS + IAM — custo zero.
2. **Ingestão** (`src/hot/lambda_raw_ingest`): event source mapping do SQS
   com `ReportBatchItemFailures` — só as mensagens que falharam voltam para
   a fila (o redrive da fila manda reincidentes para a DLQ). Um objeto por
   mensagem (chave = messageId → reprocessamento idempotente), particionado
   `year/month/day`. Roda **na VPC** e escreve no S3 via gateway endpoint.

Decisões: `arm64`, X-Ray ativo, logs 365 dias, `maximum_concurrency = 2`
no mapping (mínimo do SQS) e timeout da função ≤ visibility timeout da fila.
