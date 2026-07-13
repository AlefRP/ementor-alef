#!/bin/bash
# Bootstrap OFFLINE das APIs do lakehouse: tudo chega via S3 gateway endpoint —
# repositórios AL2023 (dnf) e bundle de wheels do bucket de artefatos.
# Log em /var/log/user-data.log, replicado no S3 ao final (sucesso ou falha):
# é o único registro de boot de uma instância privada sem SSH.
# bundle_etag=${bundle_etag} (bundle novo => user_data muda => replace da EC2)
set -euo pipefail
exec > /var/log/user-data.log 2>&1
trap 'aws s3 cp /var/log/user-data.log s3://${artifacts_bucket}/logs/user-data-${service_name}.log || true' ERR

dnf install -y python3.11

mkdir -p /opt/lakehouse
aws s3 cp 's3://${artifacts_bucket}/${bundle_key}' /opt/lakehouse/bundle.tar.gz
tar -xzf /opt/lakehouse/bundle.tar.gz -C /opt/lakehouse

python3.11 -m venv /opt/lakehouse/.venv
/opt/lakehouse/.venv/bin/pip install --no-index \
  --find-links /opt/lakehouse/wheelhouse 'aws-lakehouse-mentoria[api]'

# TLS self-signed gerado pelo Terraform (SAN = IP privado): uvicorn serve HTTPS,
# quem chama verifica contra a mesma CA. Chave 0600 (so o servico le).
mkdir -p /opt/lakehouse/certs
cat > /opt/lakehouse/certs/api.crt <<'CERT'
${tls_cert_pem}CERT
cat > /opt/lakehouse/certs/api.key <<'KEY'
${tls_key_pem}KEY
chmod 600 /opt/lakehouse/certs/api.key
chown -R ec2-user:ec2-user /opt/lakehouse

cat > /etc/systemd/system/${service_name}.service <<UNIT
[Unit]
Description=${service_description}
After=network-online.target
Wants=network-online.target

[Service]
%{ for chave, valor in service_env ~}
Environment=${chave}=${valor}
%{ endfor ~}
ExecStart=/opt/lakehouse/.venv/bin/uvicorn ${app_module} --host 0.0.0.0 --port ${api_port} --ssl-certfile /opt/lakehouse/certs/api.crt --ssl-keyfile /opt/lakehouse/certs/api.key
Restart=always
RestartSec=5
User=ec2-user

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now ${service_name}.service

aws s3 cp /var/log/user-data.log s3://${artifacts_bucket}/logs/user-data-${service_name}.log || true
