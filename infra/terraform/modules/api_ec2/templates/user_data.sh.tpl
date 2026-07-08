#!/bin/bash
# Bootstrap OFFLINE da API (camada fria): tudo chega via S3 gateway endpoint —
# repositórios AL2023 (dnf) e bundle de wheels do bucket de artefatos.
# Log em /var/log/user-data.log.
set -euo pipefail
exec > /var/log/user-data.log 2>&1

dnf install -y python3.11

mkdir -p /opt/lakehouse
aws s3 cp 's3://${artifacts_bucket}/${bundle_key}' /opt/lakehouse/bundle.tar.gz
tar -xzf /opt/lakehouse/bundle.tar.gz -C /opt/lakehouse

python3.11 -m venv /opt/lakehouse/.venv
/opt/lakehouse/.venv/bin/pip install --no-index \
  --find-links /opt/lakehouse/wheelhouse 'aws-lakehouse-mentoria[api]'
chown -R ec2-user:ec2-user /opt/lakehouse

cat > /etc/systemd/system/api-orders.service <<UNIT
[Unit]
Description=API de data product Olist (camada fria)
After=network-online.target
Wants=network-online.target

[Service]
Environment=DB_AUTH=iam
Environment=PGHOST=${pghost}
Environment=PGPORT=${pgport}
Environment=PGDATABASE=${pgdatabase}
Environment=PGUSER=${pguser}
Environment=AWS_DEFAULT_REGION=${aws_region}
ExecStart=/opt/lakehouse/.venv/bin/uvicorn src.cold.api_orders.main:app --host 0.0.0.0 --port ${api_port}
Restart=always
RestartSec=5
User=ec2-user

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now api-orders.service
