"""TAAC estático: regras de arquitetura validadas sobre o código Terraform.

Roda sem AWS e sem infra aplicada — gate imediato em qualquer CI. Cada teste
espelha um critério de aceitação das stories de infra/governança.
Helpers/fixtures vêm de tests/taac/conftest.py (injetados pelo pytest —
não importe o conftest diretamente: --import-mode=importlib sem __init__.py
não o expõe como módulo).
"""
import re

import pytest

pytestmark = pytest.mark.taac


def _by_type(resources, tf_type):
    return [r for r in resources if r.type == tf_type]


def test_every_bucket_has_block_public_access(resources):
    """Todo bucket S3 (raw, silver, state) tem os 4 flags de BPA ativos."""
    buckets = _by_type(resources, 'aws_s3_bucket')
    bpa_blocks = _by_type(resources, 'aws_s3_bucket_public_access_block')
    assert buckets, 'esperava ao menos os buckets raw/silver/state'

    flags = (
        'block_public_acls',
        'block_public_policy',
        'ignore_public_acls',
        'restrict_public_buckets',
    )
    for bpa in bpa_blocks:
        for flag in flags:
            assert re.search(
                rf'{flag}\s*=\s*true', bpa.body
            ), f'{bpa.address} em {bpa.file.name}: flag {flag} não é true'

    # Cobertura: cada declaração de bucket tem um BPA no mesmo módulo.
    for bucket in buckets:
        same_module = [b for b in bpa_blocks if b.file.parent == bucket.file.parent]
        assert same_module, (
            f'{bucket.address} ({bucket.file}) sem'
            ' aws_s3_bucket_public_access_block no módulo'
        )


def test_no_wildcard_in_iam_policies(terraform_blocks):
    """Least-privilege: nenhuma policy própria com Action ou Resource '*'."""
    policies = [b for b in terraform_blocks if b.type == 'aws_iam_policy_document']
    assert policies, 'esperava policies IAM (governance)'
    for policy in policies:
        assert not re.search(
            r'actions\s*=\s*\[\s*"\*"', policy.body
        ), f"{policy.address}: Action '*' viola least-privilege"
        assert not re.search(
            r'resources\s*=\s*\[\s*"\*"\s*\]', policy.body
        ), f"{policy.address}: Resource '*' sozinho viola least-privilege"


def test_rds_is_private_encrypted_and_passwordless(resources):
    """RDS: privado, cifrado e sem senha no código (Secrets Manager)."""
    instances = _by_type(resources, 'aws_db_instance')
    assert instances, 'esperava a instância RDS do lakehouse'
    for db in instances:
        assert not re.search(
            r'publicly_accessible\s*=\s*true', db.body
        ), f'{db.address}: RDS não pode ser público'
        assert re.search(
            r'storage_encrypted\s*=\s*true', db.body
        ), f'{db.address}: storage_encrypted deve ser true'
        assert (
            'manage_master_user_password' in db.body
        ), f'{db.address}: senha deve ser gerenciada via Secrets Manager'
        body_without_managed = db.body.replace('manage_master_user_password', '')
        assert not re.search(
            r'^\s*password\s*=', body_without_managed, re.MULTILINE
        ), f'{db.address}: senha literal detectada'


def test_sqs_queues_are_encrypted(resources):
    """Toda fila SQS (principal e DLQ) tem SSE habilitado."""
    queues = _by_type(resources, 'aws_sqs_queue')
    assert queues, 'esperava filas SQS (events + DLQ)'
    for queue in queues:
        assert re.search(
            r'sqs_managed_sse_enabled\s*=\s*true', queue.body
        ), f'{queue.address}: fila sem SSE'


def test_sqs_enforces_tls_in_transit(resources, terraform_blocks):
    """Criptografia em trânsito: toda fila SQS tem policy negando não-TLS.

    Sem VPC endpoint (custo zero), o acesso à fila é travado a HTTPS/TLS via
    statement Deny com aws:SecureTransport=false — padrão AWS de segurança.
    """
    queue_policies = _by_type(resources, 'aws_sqs_queue_policy')
    assert len(queue_policies) >= 2, 'esperava policy TLS-only na fila e na DLQ'

    deny_docs = [
        b
        for b in terraform_blocks
        if b.type == 'aws_iam_policy_document'
        and 'aws:SecureTransport' in b.body
        and re.search(r'values\s*=\s*\[\s*"false"', b.body)
    ]
    assert len(deny_docs) >= 2, 'esperava Deny non-TLS para a fila e a DLQ'
    for doc in deny_docs:
        assert re.search(
            r'effect\s*=\s*"Deny"', doc.body
        ), f'{doc.address}: SecureTransport deve ser um statement Deny'


def test_events_queue_has_dlq(resources):
    """A fila de eventos tem redrive policy apontando para a DLQ."""
    queues = _by_type(resources, 'aws_sqs_queue')
    with_redrive = [q for q in queues if 'redrive_policy' in q.body]
    assert with_redrive, 'fila de eventos sem redrive_policy (DLQ)'


def test_remote_backend_is_secure(terraform_dir):
    """Backend s3 do prod: criptografado e com lock nativo."""
    versions = terraform_dir / 'environments' / 'prod' / 'versions.tf'
    text = versions.read_text(encoding='utf-8')
    assert 'backend "s3"' in text, 'prod deve usar backend remoto s3'
    assert re.search(r'encrypt\s*=\s*true', text), 'backend sem encrypt'
    assert re.search(r'use_lockfile\s*=\s*true', text), 'backend sem lock de state'


def test_raw_and_silver_registered_in_lake_formation(resources):
    """Critério da governança: raw e silver são Data Lake Locations."""
    locations = _by_type(resources, 'aws_lakeformation_resource')
    names = {loc.name for loc in locations}
    assert {
        'raw',
        'silver',
    } <= names, f'esperava lakeformation_resource p/ raw e silver; encontrado: {names}'


def test_execution_roles_exist_one_per_service(resources):
    """Governança: uma role por serviço/função (cold, hot, glue, ec2)."""
    roles = {r.name for r in _by_type(resources, 'aws_iam_role')}
    expected = {'lambda_ingest_cold', 'lambda_ingest_hot', 'glue_job', 'ec2_api'}
    assert expected <= roles, f'roles faltando: {expected - roles}'


def test_every_lambda_caps_concurrency(resources):
    """Custo/idempotência: toda Lambda declara reserved_concurrent_executions."""
    functions = _by_type(resources, 'aws_lambda_function')
    assert functions, 'esperava as Lambdas de ingestão'
    for fn in functions:
        assert re.search(
            r'reserved_concurrent_executions\s*=', fn.body
        ), f'{fn.address}: sem limite de concorrência'


def test_ingest_lambdas_run_inside_vpc(resources):
    """Tráfego privado: Lambdas que tocam a raw rodam na VPC.

    Exceção documentada: o producer (só fala com SQS, que não tem gateway
    endpoint gratuito) roda fora da VPC.
    """
    functions = [
        f for f in _by_type(resources, 'aws_lambda_function') if f.name != 'producer'
    ]
    assert functions, 'esperava as Lambdas de ingestão (fria e quente)'
    for fn in functions:
        assert 'vpc_config' in fn.body, f'{fn.address}: Lambda fora da VPC'


def test_sqs_mapping_reports_batch_item_failures(resources):
    """Camada quente: reprocessamento granular por mensagem (não o lote)."""
    mappings = _by_type(resources, 'aws_lambda_event_source_mapping')
    assert mappings, 'esperava o event source mapping SQS -> ingestão'
    for mapping in mappings:
        assert (
            'ReportBatchItemFailures' in mapping.body
        ), f'{mapping.address}: sem ReportBatchItemFailures'


def test_api_traffic_is_tls_encrypted(terraform_dir, resources):
    """Criptografia em trânsito: API serve HTTPS e a Lambda verifica a CA.

    Cert self-signed (custo zero) gerado no apply; uvicorn sobe com --ssl-*
    e a Lambda de ingestão recebe a CA embarcada (API_CA_FILE) para validar.
    """
    user_data = (
        terraform_dir / 'modules' / 'api_ec2' / 'templates' / 'user_data.sh.tpl'
    ).read_text(encoding='utf-8')
    assert (
        '--ssl-certfile' in user_data and '--ssl-keyfile' in user_data
    ), 'uvicorn deve servir HTTPS (--ssl-certfile/--ssl-keyfile)'

    certs = _by_type(resources, 'tls_self_signed_cert')
    assert certs, 'esperava cert TLS self-signed para a API'

    cold_lambdas = [
        f
        for f in _by_type(resources, 'aws_lambda_function')
        if 'API_BASE_URL' in f.body
    ]
    assert cold_lambdas, 'esperava a Lambda de ingestão fria (chama a API)'
    for fn in cold_lambdas:
        assert (
            'API_CA_FILE' in fn.body
        ), f'{fn.address}: sem API_CA_FILE (verificação do TLS da API)'


def test_ec2_api_is_private_encrypted_and_imdsv2(resources):
    """Postura privada: EC2 sem IP público, EBS cifrado e IMDSv2."""
    instances = _by_type(resources, 'aws_instance')
    assert instances, 'esperava a EC2 da API fria'
    for inst in instances:
        assert re.search(
            r'associate_public_ip_address\s*=\s*false', inst.body
        ), f'{inst.address}: instância com IP público'
        assert re.search(
            r'http_tokens\s*=\s*"required"', inst.body
        ), f'{inst.address}: IMDSv2 não obrigatório'
        assert re.search(
            r'encrypted\s*=\s*true', inst.body
        ), f'{inst.address}: volume raiz sem criptografia'


def test_s3_gateway_endpoint_exists(resources):
    """Rede sem NAT: S3 alcançado por gateway endpoint (gratuito)."""
    endpoints = _by_type(resources, 'aws_vpc_endpoint')
    assert any(
        re.search(r'vpc_endpoint_type\s*=\s*"Gateway"', e.body) and '.s3' in e.body
        for e in endpoints
    ), 'esperava aws_vpc_endpoint Gateway para o S3'


def test_rds_uses_iam_authentication(resources):
    """Sem segredo em runtime: RDS com IAM database authentication."""
    for db in _by_type(resources, 'aws_db_instance'):
        assert re.search(
            r'iam_database_authentication_enabled\s*=\s*true', db.body
        ), f'{db.address}: IAM auth desabilitado'


def test_private_ec2_is_diagnosable(terraform_dir, resources):
    """EC2 privada sem caixa-preta: SSM por interface endpoints + log de boot.

    Sem SSH/IP público/NAT, uma falha de boot seria indiagnosticável: o
    Session Manager dá shell auditável e o user_data replica o log no S3.
    """
    endpoints = _by_type(resources, 'aws_vpc_endpoint')
    interface = [
        e
        for e in endpoints
        if re.search(r'vpc_endpoint_type\s*=\s*"Interface"', e.body)
    ]
    assert interface, 'esperava interface endpoints do SSM'
    for service in ('"ssm"', '"ssmmessages"', '"ec2messages"'):
        assert any(
            service in e.body for e in interface
        ), f'interface endpoint {service} ausente (Session Manager)'

    attachments = _by_type(resources, 'aws_iam_role_policy_attachment')
    assert any(
        'AmazonSSMManagedInstanceCore' in a.body for a in attachments
    ), 'role da EC2 sem AmazonSSMManagedInstanceCore (Session Manager)'

    user_data = (
        terraform_dir / 'modules' / 'api_ec2' / 'templates' / 'user_data.sh.tpl'
    ).read_text(encoding='utf-8')
    assert (
        'trap' in user_data and '/logs/' in user_data
    ), 'user_data deve enviar /var/log/user-data.log ao S3 em caso de falha'


def test_api_bundle_gates_instance_creation(terraform_blocks):
    """O apply valida o bundle ANTES de criar a EC2 (e replace em bundle novo).

    O user_data roda uma única vez: sem o data source do bundle, a instância
    nasceria quebrada e silenciosa; o etag no user_data força replace quando
    um bundle novo é publicado.
    """
    bundle_data = [
        b for b in terraform_blocks if b.kind == 'data' and b.type == 'aws_s3_object'
    ]
    assert bundle_data, 'esperava data aws_s3_object validando o bundle da API'

    instances = [
        b for b in terraform_blocks if b.kind == 'resource' and b.type == 'aws_instance'
    ]
    for inst in instances:
        assert (
            'bundle_etag' in inst.body
        ), f'{inst.address}: user_data sem etag do bundle (replace no redeploy)'


def test_no_ingress_rule_open_to_internet(terraform_blocks):
    """Nenhuma regra de ingress com 0.0.0.0/0 (workloads 100% privados)."""
    rules = [
        b for b in terraform_blocks if b.type == 'aws_vpc_security_group_ingress_rule'
    ]
    assert rules, 'esperava regras de ingress declaradas'
    for rule in rules:
        assert (
            '0.0.0.0/0' not in rule.body
        ), f'{rule.address}: ingress aberto à internet'


def test_cold_datasets_have_their_own_schedules(resources):
    """Datasets extras da fria: um alvo por dataset com cursor por PK.

    A mesma função atende N datasets; cada regra do EventBridge injeta
    ``{dataset, cursor_mode: pk}`` no input do alvo e o marker separa o
    estado por dataset na raw.
    """
    targets = _by_type(resources, 'aws_cloudwatch_event_target')
    dataset_targets = [t for t in targets if 'cursor_mode' in t.body]
    assert dataset_targets, (
        'esperava aws_cloudwatch_event_target com input {dataset, cursor_mode}'
        ' no módulo lambda_ingest'
    )
    for target in dataset_targets:
        assert (
            'for_each' in target.body
        ), f'{target.address}: esperava um alvo por dataset (for_each)'
        assert re.search(
            r'cursor_mode\s*=\s*"pk"', target.body
        ), f'{target.address}: cursor_mode do input deve ser "pk"'


def test_db_seeder_bootstraps_on_apply(resources):
    """O seed do RDS roda no apply que sobe a infra e re-roda se o banco mudar.

    Sem a invocação, o banco nasce vazio (sem schema e sem api_reader) e a
    camada fria inteira fica muda: a API responde 500 e a ingestão não grava
    nada na raw. O trigger em pghost re-executa o bootstrap quando o RDS é
    recriado (endpoint novo = banco vazio de novo).
    """
    invocations = _by_type(resources, 'aws_lambda_invocation')
    seeders = [b for b in invocations if 'db_seeder' in str(b.file)]
    assert seeders, 'esperava aws_lambda_invocation no módulo simulation/db_seeder'
    for invocation in seeders:
        assert re.search(
            r'triggers\s*=', invocation.body
        ), f'{invocation.address}: sem triggers (não re-roda se o RDS for recriado)'
        assert (
            'pghost' in invocation.body
        ), f'{invocation.address}: trigger deve incluir pghost (RDS novo = vazio)'
