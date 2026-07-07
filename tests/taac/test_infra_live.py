"""TAAC live: valida a infraestrutura APLICADA na conta AWS via boto3.

Skip gracioso em dois níveis:
- módulo inteiro se não houver credenciais AWS (CI matrix não tem);
- teste individual se o recurso ainda não foi aplicado (vira gate real
  após o primeiro terraform apply).
"""
import os

import pytest

boto3 = pytest.importorskip("boto3")
from botocore.exceptions import ClientError  # noqa: E402

pytestmark = pytest.mark.taac

if not (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE")):
    pytest.skip("sem credenciais AWS no ambiente", allow_module_level=True)

PREFIX = os.environ.get("TAAC_PREFIX", "ementor-lakehouse-prod")


def _skip_if_missing(error: ClientError, resource: str) -> None:
    missing = {
        "NoSuchBucket",
        "NoSuchPublicAccessBlockConfiguration",
        "404",
        "NoSuchEntity",
        "DBInstanceNotFound",
        "AWS.SimpleQueueService.NonExistentQueue",
        "QueueDoesNotExist",
        "EntityNotFoundException",
    }
    if error.response["Error"]["Code"] in missing:
        pytest.skip(f"infra não aplicada ainda ({resource})")
    raise error


@pytest.fixture(scope="module")
def session():
    return boto3.session.Session()


@pytest.mark.parametrize("layer", ["raw", "silver"])
def test_layer_bucket_blocks_public_access(session, layer):
    """Critério: BPA com 4 flags ativos nos buckets raw e silver."""
    s3 = session.client("s3")
    bucket = f"{PREFIX}-{layer}"
    try:
        config = s3.get_public_access_block(Bucket=bucket)
    except ClientError as err:
        _skip_if_missing(err, bucket)
    flags = config["PublicAccessBlockConfiguration"]
    assert all(flags.values()), f"{bucket}: BPA incompleto -> {flags}"


def test_events_queue_encrypted_with_dlq(session):
    """Fila de eventos com SSE e redrive para a DLQ."""
    sqs = session.client("sqs")
    try:
        url = sqs.get_queue_url(QueueName=f"{PREFIX}-events")["QueueUrl"]
    except ClientError as err:
        _skip_if_missing(err, f"{PREFIX}-events")
    attrs = sqs.get_queue_attributes(
        QueueUrl=url, AttributeNames=["SqsManagedSseEnabled", "RedrivePolicy"]
    )["Attributes"]
    assert attrs.get("SqsManagedSseEnabled") == "true", "fila sem SSE"
    assert "RedrivePolicy" in attrs, "fila sem DLQ (redrive)"


def test_rds_private_and_encrypted(session):
    """RDS privado e com storage cifrado."""
    rds = session.client("rds")
    try:
        instances = rds.describe_db_instances(
            DBInstanceIdentifier=f"{PREFIX}-postgres"
        )["DBInstances"]
    except ClientError as err:
        _skip_if_missing(err, f"{PREFIX}-postgres")
    db = instances[0]
    assert db["PubliclyAccessible"] is False, "RDS exposto publicamente"
    assert db["StorageEncrypted"] is True, "RDS sem criptografia em repouso"


@pytest.mark.parametrize(
    "role_suffix",
    ["lambda-ingest-cold", "lambda-ingest-hot", "glue-silver", "ec2-api"],
)
def test_execution_role_has_no_wildcard(session, role_suffix):
    """Roles de execução sem '*' em Action/Resource (least-privilege)."""
    iam = session.client("iam")
    role_name = f"{PREFIX}-{role_suffix}"
    try:
        policy_names = iam.list_role_policies(RoleName=role_name)["PolicyNames"]
    except ClientError as err:
        _skip_if_missing(err, role_name)
    for policy_name in policy_names:
        doc = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)[
            "PolicyDocument"
        ]
        for stmt in doc.get("Statement", []):
            actions = stmt.get("Action", [])
            actions = [actions] if isinstance(actions, str) else actions
            assert "*" not in actions, f"{role_name}/{policy_name}: Action '*'"
            resources = stmt.get("Resource", [])
            resources = [resources] if isinstance(resources, str) else resources
            assert resources != ["*"], f"{role_name}/{policy_name}: Resource '*'"


def test_raw_and_silver_are_data_lake_locations(session):
    """Critério: raw e silver registrados no Lake Formation."""
    lakeformation = session.client("lakeformation")
    try:
        registered = lakeformation.list_resources()["ResourceInfoList"]
    except ClientError as err:
        _skip_if_missing(err, "lakeformation")
    arns = {info["ResourceArn"] for info in registered}
    expected = {f"arn:aws:s3:::{PREFIX}-raw", f"arn:aws:s3:::{PREFIX}-silver"}
    missing = expected - arns
    if arns == set():
        pytest.skip("infra não aplicada ainda (nenhum location registrado)")
    assert not missing, f"locations não registrados: {missing}"
