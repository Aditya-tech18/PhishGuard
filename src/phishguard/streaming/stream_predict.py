"""Spark Structured Streaming Kafka inference with checkpointed offsets.

Sink is append-only Parquet. Checkpoints recover offsets; downstream event_id
is the dedup key. Model path must exist at the same location on every executor.
Do not run concurrent queries against the same checkpoint.
"""

from pathlib import Path
from phishguard.features.url_features import normalize_url


def start_stream(spark, model_path, bootstrap, output, checkpoint, available_now=False):
    from pyspark.sql import functions as F, types as T

    model_path = str(Path(model_path).resolve(strict=True))
    output = Path(output).resolve()
    checkpoint = Path(checkpoint).resolve()
    if output == checkpoint or output in checkpoint.parents or checkpoint in output.parents:
        raise ValueError("Output and checkpoint must be separate directories")
    schema = T.StructType(
        [
            T.StructField("event_id", T.StringType()),
            T.StructField("timestamp", T.StringType()),
            T.StructField("url", T.StringType()),
            T.StructField("schema_version", T.IntegerType()),
        ]
    )
    result_schema = T.StructType(
        [
            T.StructField("probability", T.DoubleType()),
            T.StructField("verdict", T.StringType()),
            T.StructField("model_version", T.StringType()),
            T.StructField("error", T.StringType()),
        ]
    )

    def score(event_id, timestamp, url, schema_version):
        from phishguard.common.schemas import URLEvent
        from phishguard.ml.model_registry import URLModel

        try:
            event = URLEvent(
                event_id=event_id, timestamp=timestamp, url=url, schema_version=schema_version
            )
        except (ValueError, TypeError):
            return None, None, None, "invalid_event"
        # Cache per Python worker, not one file read per record.
        if not hasattr(score, "model"):
            score.model = URLModel.load(model_path)
        result = score.model.predict(normalize_url(event.url))
        return result["probability"], result["verdict"], result["model_version"], None

    predict = F.udf(score, result_schema)
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", "phishguard.raw_urls")
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "true")
        .option("maxOffsetsPerTrigger", 1000)
        .load()
    )
    decoded = raw.select(
        "topic",
        "partition",
        "offset",
        F.from_json(F.col("value").cast("string"), schema).alias("event"),
    )
    scored = decoded.withColumn(
        "prediction",
        predict("event.event_id", "event.timestamp", "event.url", "event.schema_version"),
    )
    # Deliberately omit raw URL and raw payload from ALL output rows, including rejects.
    final = scored.select(
        "topic",
        "partition",
        "offset",
        F.col("event.event_id").alias("event_id"),
        F.to_timestamp("event.timestamp").alias("timestamp"),
        "prediction.*",
    )
    writer = (
        final.writeStream.format("parquet")
        .outputMode("append")
        .option("path", str(output))
        .option("checkpointLocation", str(checkpoint))
    )
    writer = (
        writer.trigger(availableNow=True)
        if available_now
        else writer.trigger(processingTime="10 seconds")
    )
    return writer.start()
