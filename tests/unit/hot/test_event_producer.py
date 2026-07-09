"""Testes da Lambda produtora de eventos sintéticos (camada quente)."""
import json
from datetime import datetime, timezone
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.hot.event_producer import handler as producer

QUEUE = 'eventos-teste'


@pytest.fixture()
def producer_env(monkeypatch):
    """Ambiente mínimo da Lambda com client SQS zerado por teste."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    producer._SQS = None
    yield
    producer._SQS = None


def _create_queue(monkeypatch):
    url = boto3.client('sqs').create_queue(QueueName=QUEUE)['QueueUrl']
    monkeypatch.setenv('QUEUE_URL', url)
    return url


@mock_aws
def test_handler_publishes_all_events(producer_env, monkeypatch):
    url = _create_queue(monkeypatch)
    monkeypatch.setenv('EVENTS_PER_RUN', '25')

    result = producer.handler({}, None)

    assert result == {'statusCode': 200, 'published': 25}
    attrs = boto3.client('sqs').get_queue_attributes(
        QueueUrl=url, AttributeNames=['ApproximateNumberOfMessages']
    )['Attributes']
    assert int(attrs['ApproximateNumberOfMessages']) == 25


@mock_aws
def test_published_message_is_valid_olist_event(producer_env, monkeypatch):
    url = _create_queue(monkeypatch)
    monkeypatch.setenv('EVENTS_PER_RUN', '1')

    producer.handler({}, None)

    message = boto3.client('sqs').receive_message(QueueUrl=url)['Messages'][0]
    event = json.loads(message['Body'])
    assert event['event_type'].startswith('order_')
    assert event['customer']['customer_state'] in producer.CUSTOMER_STATES
    assert event['payment']['payment_type'] in producer.PAYMENT_TYPES
    assert event['event_id'] and event['order']['order_id']
    # Faker preencheu os campos realistas (nome/cidade não vazios).
    assert event['customer']['customer_name']
    assert event['customer']['customer_city']


def test_new_event_uses_moment_timestamp():
    moment = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
    event = producer._new_event(moment)
    assert event['event_timestamp'] == '2026-07-08T12:00:00+00:00'
    assert 1 <= event['order']['items_count'] <= 4


@mock_aws
def test_handler_raises_when_sqs_rejects_messages(producer_env, monkeypatch):
    _create_queue(monkeypatch)
    monkeypatch.setenv('EVENTS_PER_RUN', '3')
    fake = mock.Mock()
    fake.send_message_batch.return_value = {'Failed': [{'Id': '0'}]}
    with mock.patch.object(producer, '_sqs_client', return_value=fake):
        with pytest.raises(RuntimeError):
            producer.handler({}, None)


@mock_aws
def test_handler_propagates_missing_queue(producer_env, monkeypatch):
    monkeypatch.setenv(
        'QUEUE_URL',
        'https://queue.amazonaws.com/123456789012/inexistente',
    )
    monkeypatch.setenv('EVENTS_PER_RUN', '1')
    with pytest.raises(ClientError):
        producer.handler({}, None)
