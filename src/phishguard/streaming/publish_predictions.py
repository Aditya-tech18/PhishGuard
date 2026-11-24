"""Stable event IDs let downstream consumers deduplicate at-least-once delivery."""

from phishguard.common.schemas import Prediction
from phishguard.streaming.kafka_producer import publish


def publish_prediction(client, event, model, topic="phishguard.predictions"):
    prediction = Prediction(
        event_id=event.event_id, timestamp=event.timestamp, **model.predict(event.url)
    )
    publish(client, topic, prediction.event_id, prediction.model_dump(mode="json"))
    return prediction


def publish_dead_letter(client, message, reason, topic="phishguard.dead_letter"):
    # Raw corrupt payloads may contain credentials, so never forward them to the DLQ.
    key = f"{message.topic()}:{message.partition()}:{message.offset()}"
    publish(
        client,
        topic,
        key,
        {
            "source_topic": message.topic(),
            "partition": message.partition(),
            "offset": message.offset(),
            "reason": reason,
            "schema_version": 1,
        },
    )
