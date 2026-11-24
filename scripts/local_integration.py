#!/usr/bin/env python3
"""Run an isolated Kafka 4.x broker and optional real Spark streaming integration.

Requires local Kafka tools, JDK 21 for Kafka 4, JDK 17 for Spark, and installed extras.
Writes only to a new scratch directory. Does not use your normal broker/data directory.
The test producer submits only synthetic example URLs. No API secrets are required.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid


def free_port(port):
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", port))


def wait_broker(process, port, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Broker exited; inspect broker.log in the scratch directory")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError("Isolated broker startup timed out")


def check_consumer(model, bootstrap):
    from confluent_kafka import Consumer
    from confluent_kafka.admin import AdminClient, NewTopic
    from phishguard.streaming.kafka_consumer import consume
    from phishguard.streaming.kafka_producer import kafka_config, producer, publish_url

    os.environ["PHISHGUARD_KAFKA_BOOTSTRAP"] = bootstrap
    admin = AdminClient(kafka_config())
    for future in admin.create_topics(
        [
            NewTopic("phishguard." + name, 1, 1)
            for name in ["raw_urls", "predictions", "dead_letter"]
        ]
    ).values():
        future.result(20)
    output = producer()
    event_id = publish_url(output, "https://example.com/")
    count = consume(model, max_messages=1, group="integration-" + uuid.uuid4().hex)
    reader = Consumer(
        {
            **kafka_config(),
            "group.id": uuid.uuid4().hex,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    try:
        reader.subscribe(["phishguard.predictions"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = reader.poll(1)
            if message and not message.error():
                payload = json.loads(message.value())
                if payload["event_id"] != event_id or "url" in payload:
                    raise RuntimeError("Output identity/minimization contract failed")
                return {"processed": count, "stable_event_id": True, "raw_url_omitted": True}
        raise TimeoutError("Acknowledged prediction not received")
    finally:
        reader.close()
        output.flush(5)


def check_crash_replay(model):
    """Inject a crash after acknowledged output but before commit, then restart same group."""
    import phishguard.streaming.kafka_consumer as module
    from confluent_kafka import Consumer
    from phishguard.streaming.kafka_producer import kafka_config

    group = "crash-replay-" + uuid.uuid4().hex
    original = module.process_message

    def fail_after_output(message, client, predictor):
        original(message, client, predictor)
        raise RuntimeError("Injected crash between output acknowledgement and offset commit")

    module.process_message = fail_after_output
    try:
        try:
            module.consume(model, max_messages=1, group=group)
        except RuntimeError as exc:
            if "Injected crash" not in str(exc):
                raise
        else:
            raise RuntimeError("Crash injection did not interrupt consumption")
    finally:
        module.process_message = original
    module.consume(model, max_messages=1, group=group)
    reader = Consumer(
        {
            **kafka_config(),
            "group.id": uuid.uuid4().hex,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    try:
        reader.subscribe(["phishguard.predictions"])
        events = []
        deadline = time.monotonic() + 30
        while len(events) < 3 and time.monotonic() < deadline:
            message = reader.poll(1)
            if message and not message.error():
                events.append(json.loads(message.value()))
        if len(events) != 3 or len({event["event_id"] for event in events}) != 1:
            raise RuntimeError(
                "Expected acknowledged original, interrupted output and replay duplicate"
            )
        if any("url" in event for event in events):
            raise RuntimeError("Raw URL leaked into replay output")
        return {
            "crash_window_replayed": True,
            "prediction_rows": 3,
            "unique_event_ids": 1,
            "guarantee": "at_least_once_requires_deduplication",
        }
    finally:
        reader.close()


def check_spark(model, scratch, bootstrap, spark_java):
    from phishguard.streaming.kafka_producer import producer, publish_url, publish
    from phishguard.processing.spark_session import create_spark
    from phishguard.streaming.stream_predict import start_stream

    client = producer()
    publish_url(client, "http://verify-account.test/login")
    publish(client, "phishguard.raw_urls", "poison", {"bad": "must-not-leak"})
    os.environ["JAVA_HOME"] = str(spark_java)
    os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_SUBMIT_ARGS"] = f"--conf spark.jars.ivy={scratch / 'ivy'} pyspark-shell"
    spark = create_spark(kafka=True)
    query = None
    try:
        output, checkpoint = scratch / "predictions", scratch / "checkpoints"
        query = start_stream(spark, model, bootstrap, output, checkpoint, available_now=True)
        if not query.awaitTermination(120):
            raise TimeoutError("First Spark query did not terminate")
        frame = spark.read.parquet(str(output))
        if frame.count() != 3 or frame.where("error IS NOT NULL").count() != 1:
            raise RuntimeError("Expected 2 valid events and 1 minimized rejection")
        if "url" in frame.columns or "must-not-leak" in str(frame.collect()):
            raise RuntimeError("Raw payload was persisted")
        query = start_stream(spark, model, bootstrap, output, checkpoint, available_now=True)
        if not query.awaitTermination(60):
            raise TimeoutError("Checkpoint restart did not terminate")
        if spark.read.parquet(str(output)).count() != 3:
            raise RuntimeError("Checkpoint restart wrote unexpected rows")
        return {
            "rows": 3,
            "invalid_rows": 1,
            "url_omitted": True,
            "checkpoint_restart_no_extra_rows": True,
        }
    finally:
        if query is not None and query.isActive:
            query.stop()
        spark.stop()
        client.flush(5)


def run(args):
    from phishguard.ml.model_registry import URLModel

    URLModel.load(args.model)
    for port in [args.port, args.port + 1]:
        free_port(port)
    scratch = args.work_dir.absolute() / ("kafka-integration-" + uuid.uuid4().hex[:10])
    scratch.mkdir(parents=True, exist_ok=False, mode=0o700)
    config = scratch / "server.properties"
    config.write_text(f"""process.roles=broker,controller
node.id=1
controller.quorum.bootstrap.servers=127.0.0.1:{args.port + 1}
listeners=PLAINTEXT://127.0.0.1:{args.port},CONTROLLER://127.0.0.1:{args.port + 1}
advertised.listeners=PLAINTEXT://127.0.0.1:{args.port}
controller.listener.names=CONTROLLER
listener.security.protocol.map=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=PLAINTEXT
log.dirs={scratch / "broker-data"}
num.partitions=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
log.retention.hours=1
""")
    env = dict(
        os.environ,
        JAVA_HOME=str(args.kafka_java),
        KAFKA_HEAP_OPTS="-Xmx256m -Xms128m",
        LOG_DIR=str(scratch / "server-logs"),
    )
    cluster_id = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
    with (scratch / "format.log").open("w") as log:
        subprocess.run(
            [
                str(args.kafka_bin / "kafka-storage"),
                "format",
                "--standalone",
                "-t",
                cluster_id,
                "-c",
                str(config),
            ],
            env=env,
            check=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    with (scratch / "broker.log").open("w") as log:
        process = subprocess.Popen(
            [str(args.kafka_bin / "kafka-server-start"), str(config)],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_broker(process, args.port)
            bootstrap = f"127.0.0.1:{args.port}"
            report = {"consumer": check_consumer(args.model, bootstrap)}
            report["crash_replay"] = check_crash_replay(args.model)
            if args.spark:
                if args.spark_java is None:
                    raise ValueError("--spark-java is required with --spark")
                report["spark"] = check_spark(args.model, scratch, bootstrap, args.spark_java)
            (scratch / "result.json").write_text(json.dumps(report, indent=2))
            return {"scratch": str(scratch), **report}
        finally:
            process.terminate()
            try:
                process.wait(20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kafka-bin", type=Path, required=True)
    parser.add_argument("--kafka-java", type=Path, required=True)
    parser.add_argument("--spark-java", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("reports/local/integration"))
    parser.add_argument("--port", type=int, default=19092)
    parser.add_argument("--spark", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65534:
        raise SystemExit("Choose a nonprivileged port below 65535")
    args.model = args.model.resolve(strict=True)
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
