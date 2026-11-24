import json
import os
from uuid import uuid4
import pytest
from phishguard.streaming.kafka_consumer import process_message
from phishguard.ml.model_registry import URLModel


class Message:
    def __init__(self, value):
        self.payload = value

    def value(self):
        return self.payload

    def topic(self):
        return "test"

    def partition(self):
        return 0

    def offset(self):
        return 42


class Producer:
    def __init__(self, fail=False):
        self.records = []
        self.fail = fail

    def produce(self, topic, key, value, on_delivery):
        self.records.append((topic, json.loads(value)))
        if not self.fail:
            on_delivery(None, None)

    def flush(self, timeout):
        return 1 if self.fail else 0


def test_poison_message_minimized(model_path):
    producer = Producer()
    assert (
        process_message(Message(b"supersecret-not-json"), producer, URLModel.load(model_path))
        == "dead_letter"
    )
    assert "supersecret" not in json.dumps(producer.records)
    assert producer.records[0][1]["offset"] == 42


def test_no_success_on_failed_delivery(model_path):
    with pytest.raises(RuntimeError):
        process_message(Message(b"invalid"), Producer(fail=True), URLModel.load(model_path))


def test_stable_event_identity(model_path):
    from phishguard.common.schemas import URLEvent

    event = URLEvent(url="https://example.com")
    producer = Producer()
    for _ in range(2):
        process_message(
            Message(event.model_dump_json().encode()), producer, URLModel.load(model_path)
        )
    assert producer.records[0][1]["event_id"] == producer.records[1][1]["event_id"]
    assert "url" not in producer.records[0][1]


@pytest.mark.kafka
def test_real_broker_round_trip(model_path):
    if os.getenv("PHISHGUARD_TEST_KAFKA") != "true":
        pytest.skip("Set PHISHGUARD_TEST_KAFKA=true for isolated broker")
    from confluent_kafka.admin import AdminClient, NewTopic
    from confluent_kafka import Consumer
    from phishguard.streaming.kafka_producer import producer, kafka_config, publish_url
    import time

    topic = "phishguard-test-" + uuid4().hex
    admin = AdminClient(kafka_config())
    admin.create_topics([NewTopic(topic, 1, 1)])[topic].result(30)
    reader = Consumer(
        {
            **kafka_config(),
            "group.id": uuid4().hex,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    try:
        reader.subscribe([topic])
        identifier = publish_url(producer(), "https://example.com", topic)
        end = time.monotonic() + 30
        message = None
        while time.monotonic() < end:
            message = reader.poll(1)
            if message and not message.error():
                break
        assert message is not None and not message.error()
        assert json.loads(message.value())["event_id"] == identifier
        out = Producer()
        assert process_message(message, out, URLModel.load(model_path)) == "predicted"
    finally:
        reader.close()
        admin.delete_topics([topic])[topic].result(30)
