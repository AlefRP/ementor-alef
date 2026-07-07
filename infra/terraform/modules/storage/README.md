# Módulo storage

Buckets S3 das camadas do lakehouse (`raw`, `silver` por padrão), todos com:

- **Block Public Access** (4 flags) — critério de aceitação da story;
- versionamento + SSE (AES256, bucket key);
- policy TLS-only (nega transporte inseguro);
- lifecycle de higiene (multipart incompleto, versões antigas).

Outputs `bucket_arns`/`bucket_ids` alimentam o módulo `governance` (Lake
Formation + IAM least-privilege).
