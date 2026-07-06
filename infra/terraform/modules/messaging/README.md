# Módulo messaging

Fila SQS de eventos da camada quente (`events`) com DLQ (`events-dlq`):

- SSE gerenciado pelo SQS em ambas;
- long polling (10s) na principal;
- redrive: após `max_receive_count` tentativas a mensagem vai à DLQ (retenção
  de 14 dias para investigação);
- `redrive_allow_policy` restringe a DLQ à fila principal.

`visibility_timeout_seconds` deve ser ~6x o timeout da Lambda consumidora.
