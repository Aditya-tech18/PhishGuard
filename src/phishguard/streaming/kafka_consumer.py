"""At-least-once stream inference: commit offsets only after acknowledged output or DLQ."""

import json
from phishguard.common.schemas import URLEvent
from phishguard.streaming.kafka_producer import kafka_config, producer
from phishguard.streaming.publish_predictions import publish_prediction, publish_dead_letter
from phishguard.ml.model_registry import URLModel


def process_message(message, output, model):
    raw = message.value()
    try:
        if not raw or len(raw) > 65536:
            raise ValueError("Invalid message size")
        event = URLEvent.model_validate(json.loads(raw))
    except (ValueError, TypeError, UnicodeError):
        publish_dead_letter(output, message, "invalid_event")
        return "dead_letter"
    publish_prediction(output, event, model)
    return "predicted"


def consume(model_path, stop=None, max_messages=None, group="phishguard-v2"):
    from confluent_kafka import Consumer, KafkaException

    consumer = Consumer(
        {
            **kafka_config(),
            "group.id": group,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
        }
    )
    output = producer()
    model = URLModel.load(model_path)
    consumer.subscribe(["phishguard.raw_urls"])
    count = 0
    try:
        while stop is None or not stop.is_set():
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                raise KafkaException(message.error())
            process_message(message, output, model)
            consumer.commit(message=message, asynchronous=False)
            count += 1
            if max_messages is not None and count >= max_messages:
                break
    finally:
        consumer.close()
        output.flush(35)
    return count
