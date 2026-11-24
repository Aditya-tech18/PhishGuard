# Batch and streaming operation

## Batch ETL

```bash
phishguard batch path/to/source.csv --output data/processed/run-001 \
  --url-column url --label-column label
```

Output must be a new directory outside the input. The ETL reads CSV with FAILFAST parsing,
normalizes through the shared Python function, rejects invalid values, checks conflicting
labels, removes duplicate URLs and computes the fixed lexical feature vector. It writes:

- `gold/`: URL, label, ordered vector and named numeric feature columns in Snappy Parquet.
- `reject_summary/`: counts by rejection category without rejected raw payloads.
- `label_counts/`: class distribution after normalization and deduplication.

This is an offline sensitive-data workflow: gold contains URLs. No API URL is automatically
inserted into gold. Paths should be access-controlled and excluded from Git. On interrupted
output, retain the failed run for diagnosis or choose a fresh run path; there is no silent
`overwrite` retry. Spark may leave partial directories when a job fails.

## Kafka producer and Python inference

Configure a local broker and create explicit topics:

```bash
export PHISHGUARD_KAFKA_BOOTSTRAP=localhost:9092
phishguard topics
phishguard publish 'https://example.com/'
phishguard consume --model models/trained/url-model.json
```

The raw topic contains the submitted URL, event UUID, timezone-aware timestamp and schema
version 1. Publication is a deliberate opt-in separate from browser scanning. The topic helper
uses three partitions, single-node replication and one-hour retention for a demo cluster.
Those settings are not resilient production defaults. Change replication and retention for
your cluster and implement ACLs before accepting multiple users.

Producer output is acknowledged with `acks=all`, idempotence and a delivery callback. Delivery
failure raises instead of returning success. Consumer auto-commit and auto-offset-store are
disabled. The sequence is validate → predict → acknowledge output → commit offset. Invalid
events get a minimized DLQ record containing source topic/partition/offset and a reason, never
the raw corrupt payload. A DLQ delivery failure leaves the input uncommitted and stops processing.

Valid prediction output retains event identity and timestamp but omits URL. It includes
probability, verdict, model version and positive feature contribution names. Multiple distinct
URLs in one raw event are not accepted; schema validation forbids extra fields.

## Replay and duplicate handling

A crash after acknowledged output and before offset commit causes duplication on replay.
Consumers must upsert by event UUID or deduplicate before aggregates. The sample analytics
uses `dropDuplicates(event_id)` on offline data. Do not claim exactly-once delivery. A model
change can produce different results for the same replayed UUID; version-aware stores should
choose an explicit update policy.

Use a fresh group ID for deliberate reprocessing. Do not reset offsets casually. Retention
expiry can lose raw inputs independently of committed offsets. Monitor consumer lag and DLQ
counts using broker tooling. The runtime does not export Prometheus metrics or manage alerts.

## Spark Structured Streaming

From an installed environment:

```python
from phishguard.processing.spark_session import create_spark
from phishguard.streaming.stream_predict import start_stream
spark = create_spark(kafka=True)
query = start_stream(spark, 'models/trained/url-model.json', 'localhost:9092',
                     'data/streaming/run-001', 'data/streaming/checkpoints/run-001')
query.awaitTermination()
```

Spark 3.5.8 requires the matching Scala 2.12 Kafka connector. First run may download Maven
jars. Checkpoint and output paths must be different, non-nested directories. Never share a
checkpoint across jobs. `failOnDataLoss=true` fails when offsets disappear. `maxOffsetsPerTrigger`
bounds input per batch. Invalid events are retained as minimized error rows with source offsets.

`available_now=True` makes a bounded catch-up run. Raw topics and all required partitions must
exist before the query starts. In a cluster, install the Python package and mount the model
at the same path on every worker. A local-driver file is not automatically distributed.
The Spark connector currently exposes only the local plaintext bootstrap argument; do not use
this helper against a remote secure cluster without adding its TLS/SASL Spark options.

## Operational source references

The connector and offset semantics follow the Apache Spark documentation:
[Structured Streaming + Kafka 3.5.8](https://spark.apache.org/docs/3.5.8/structured-streaming-kafka-integration.html).
Kafka writes can duplicate; checkpointing alone does not create an end-to-end exactly-once
contract. Consult the version-specific guide before upgrading Spark/Scala/connector versions.

## Repeat the isolated integration check

For a local Kafka 4.x installation, the bundled helper creates a fresh scratch broker,
verifies real consumer delivery and optionally verifies Kafka → Spark → Parquet plus checkpoint
restart. It stops its own broker when finished and retains its scratch logs for inspection.
It does not connect to or modify your normal broker. Use paths appropriate to your machine:

```bash
python scripts/local_integration.py \
  --kafka-bin /opt/homebrew/opt/kafka/bin \
  --kafka-java /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
  --spark-java /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  --model models/trained/demo-only.json --spark
```

The helper's first Spark run downloads matching connector jars into its scratch Ivy cache.
This helper targets Kafka 4's dynamic controller quorum and is separate from the Kafka 3.9
Compose example. Do not mix the two configuration styles. All submitted URLs are synthetic
examples. The result is an integration result, not a model-quality benchmark.
