"""Acknowledged Kafka writes. No fire-and-forget success reporting."""

import json
import os
from phishguard.common.schemas import URLEvent


def kafka_config():
    config = {
        "bootstrap.servers": os.getenv("PHISHGUARD_KAFKA_BOOTSTRAP", "localhost:9092"),
        "client.id": "phishguard",
        "socket.timeout.ms": 10000,
    }
    protocol = os.getenv("PHISHGUARD_KAFKA_PROTOCOL", "PLAINTEXT")
    if protocol not in {"PLAINTEXT", "SASL_SSL", "SSL"}:
        raise ValueError("Unsupported Kafka security protocol")
    config["security.protocol"] = protocol
    if protocol == "SASL_SSL":
        for name, variable in (
            ("sasl.username", "PHISHGUARD_KAFKA_USER"),
            ("sasl.password", "PHISHGUARD_KAFKA_PASSWORD"),
        ):
            config[name] = os.environ[variable]
        config["sasl.mechanism"] = os.getenv("PHISHGUARD_KAFKA_MECHANISM", "SCRAM-SHA-512")
    if os.getenv("PHISHGUARD_KAFKA_CA"):
        config["ssl.ca.location"] = os.environ["PHISHGUARD_KAFKA_CA"]
    return config


def producer():
    from confluent_kafka import Producer

    return Producer(
        {
            **kafka_config(),
            "acks": "all",
            "enable.idempotence": True,
            "delivery.timeout.ms": 30000,
            "message.max.bytes": 100000,
        }
    )


def publish(client, topic, key, value):
    errors = []
    delivered = []

    def delivery(error, message):
        if error:
            errors.append(str(error.code()))
        else:
            delivered.append(True)

    encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 65536:
        raise ValueError("Kafka event exceeds 64 KiB")
    client.produce(topic, key=str(key).encode(), value=encoded, on_delivery=delivery)
    remaining = client.flush(35)
    if remaining or errors or not delivered:
        raise RuntimeError("Kafka delivery was not acknowledged")


def publish_url(client, url, topic="phishguard.raw_urls"):
    event = URLEvent(url=url)
    publish(client, topic, event.event_id, event.model_dump(mode="json"))
    return str(event.event_id)
