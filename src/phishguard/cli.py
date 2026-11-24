"""Command line orchestration. Heavy optional dependencies loaded only when requested."""

import argparse
import json
from pathlib import Path


def parser():
    root = argparse.ArgumentParser(prog="phishguard")
    root.add_argument("--version", action="version", version="PhishGuard 2.6.1")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("inspect", "train", "batch"):
        cmd = commands.add_parser(name)
        cmd.add_argument("input", type=Path)
        cmd.add_argument("--url-column", default="url")
        cmd.add_argument("--label-column", default="label")
        cmd.add_argument("--delimiter", default=",")
        cmd.add_argument("--positive", default="1", help="Source label meaning phishing")
        cmd.add_argument("--negative", default="0", help="Source label meaning legitimate")
        if name in {"train", "batch"}:
            cmd.add_argument("--output", type=Path, required=True)
        if name == "train":
            cmd.add_argument("--report", type=Path, default=Path("reports/local/training.json"))
    tournament = commands.add_parser("train-all")
    tournament.add_argument("input", type=Path)
    tournament.add_argument("--output", type=Path, required=True)
    tournament.add_argument("--profile", choices=["fast", "standard"], default="standard")
    tournament.add_argument("--query-policy", choices=["strip", "retain"], default="strip")
    tournament.add_argument("--bootstrap", type=int, default=200)
    tournament.add_argument("--delimiter", default=",")
    tournament.add_argument("--url-column", default="url")
    tournament.add_argument("--label-column", default="label")
    tournament.add_argument("--positive", default="1")
    tournament.add_argument("--negative", default="0")
    predict = commands.add_parser("predict")
    predict.add_argument("url")
    predict.add_argument("--model", type=Path, required=True)
    stream = commands.add_parser("consume")
    stream.add_argument("--model", type=Path, required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("url")
    commands.add_parser("topics")
    inventory = commands.add_parser("inventory")
    inventory.add_argument("root", type=Path)
    inventory.add_argument("--hash", action="store_true")
    vision = commands.add_parser("train-vision")
    vision.add_argument("root", type=Path)
    vision.add_argument("--output", type=Path, required=True)
    vision.add_argument("--epochs", type=int, default=10)
    vision.add_argument("--manifest", type=Path)
    vision.add_argument("--batch-size", type=int, default=16)
    vision.add_argument("--cache-dir", type=Path)
    vision.add_argument("--architecture", choices=["global-v1", "spatial-v2"], default="spatial-v2")
    vision.add_argument("--device", choices=["cpu", "mps", "cuda"], default="cpu")
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("input", type=Path)
    evaluation.add_argument("--model", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--reference-report", type=Path)
    evaluation.add_argument("--bootstrap", type=int, default=100)
    evaluation.add_argument("--delimiter", default=",")
    evaluation.add_argument("--url-column", default="url")
    evaluation.add_argument("--label-column", default="label")
    evaluation.add_argument("--positive", default="1")
    evaluation.add_argument("--negative", default="0")
    register = commands.add_parser("registry-register")
    register.add_argument("--root", type=Path, required=True)
    register.add_argument("--model", type=Path, required=True)
    register.add_argument("--report", type=Path, required=True)
    activate = commands.add_parser("registry-activate")
    activate.add_argument("--root", type=Path, required=True)
    activate.add_argument("--version", required=True)
    activate.add_argument("--min-precision", type=float, default=0.9)
    activate.add_argument("--min-recall", type=float, default=0.8)
    activate.add_argument("--max-fpr", type=float, default=0.05)
    activate.add_argument("--min-test-rows", type=int, default=100)
    listing = commands.add_parser("registry-list")
    listing.add_argument("--root", type=Path, required=True)
    streaming = commands.add_parser("spark-stream")
    streaming.add_argument("--model", type=Path, required=True)
    streaming.add_argument("--bootstrap", default="localhost:9092")
    streaming.add_argument("--output", type=Path, required=True)
    streaming.add_argument("--checkpoint", type=Path, required=True)
    streaming.add_argument("--available-now", action="store_true")
    analytics = commands.add_parser("analytics")
    analytics.add_argument("input", type=Path)
    analytics.add_argument("--output", type=Path, required=True)
    images = commands.add_parser("images-etl")
    images.add_argument("--legitimate-root", type=Path, required=True)
    images.add_argument("--phishing-root", type=Path, required=True)
    images.add_argument("--output", type=Path, required=True)
    showcase = commands.add_parser("launch", aliases=["showcase"])
    showcase.add_argument("--model", type=Path, required=True)
    showcase.add_argument("--evaluation", type=Path)
    showcase.add_argument("--vision-model", type=Path)
    showcase.add_argument("--quality", type=Path)
    showcase.add_argument("--pipeline", type=Path)
    showcase.add_argument("--runtime-root", type=Path, default=Path("reports/local/showcase"))
    showcase.add_argument("--api-port", type=int, default=8000)
    showcase.add_argument("--dashboard-port", type=int, default=8501)
    showcase.add_argument("--check-only", action="store_true")
    showcase.add_argument("--run-seconds", type=float, default=0)
    prepare_images = commands.add_parser("prepare-images")
    prepare_images.add_argument("root", type=Path)
    prepare_images.add_argument("--output", type=Path, required=True)
    prepare_images.add_argument("--filename-hosts", action="store_true")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command in {"launch", "showcase"}:
        from phishguard.showcase import ShowcaseConfig, preflight, run
        import signal
        import threading

        config = ShowcaseConfig(
            model=args.model,
            evaluation=args.evaluation,
            vision_model=args.vision_model,
            quality=args.quality,
            pipeline=args.pipeline,
            runtime_root=args.runtime_root,
            api_port=args.api_port,
            dashboard_port=args.dashboard_port,
            run_seconds=args.run_seconds,
        )
        if args.check_only:
            result = preflight(config)
        else:
            stop = threading.Event()
            signal.signal(signal.SIGINT, lambda *_: stop.set())
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            result = run(config, stop)
    elif args.command in {"inspect", "train", "batch"}:
        if args.positive == args.negative:
            raise SystemExit("Positive and negative labels must differ")
        options = {
            "url_column": args.url_column,
            "label_column": args.label_column,
            "delimiter": args.delimiter,
        }
        if args.command == "batch":
            from phishguard.processing.spark_session import create_spark
            from phishguard.processing.write_parquet import batch_etl

            spark = create_spark()
            try:
                result = batch_etl(
                    spark,
                    args.input,
                    args.output,
                    **options,
                    positive=args.positive,
                    negative=args.negative,
                )
            finally:
                spark.stop()
        else:
            options["label_map"] = {args.positive: 1, args.negative: 0}
            if args.command == "inspect":
                from phishguard.ingestion.inspect_dataset import inspect

                result = inspect(args.input, **options)
            else:
                from phishguard.ml.train_models import train

                result = train(args.input, args.output, args.report, **options)
    elif args.command == "train-all":
        from phishguard.ml.tournament import train_tournament

        if args.positive == args.negative:
            raise SystemExit("Positive and negative labels must differ")
        result = train_tournament(
            args.input,
            args.output,
            profile=args.profile,
            query_policy=args.query_policy,
            bootstrap_repetitions=args.bootstrap,
            delimiter=args.delimiter,
            url_column=args.url_column,
            label_column=args.label_column,
            label_map={args.positive: 1, args.negative: 0},
        )
    elif args.command == "prepare-images":
        from phishguard.ml.prepare_images import prepare

        result = prepare(args.root, args.output, filename_hosts=args.filename_hosts)
    elif args.command == "evaluate":
        from phishguard.ml.offline_evaluation import evaluate_file

        if args.positive == args.negative:
            raise SystemExit("Positive and negative labels must differ")
        result = evaluate_file(
            args.model,
            args.input,
            args.output,
            reference_report=args.reference_report,
            bootstrap=args.bootstrap,
            delimiter=args.delimiter,
            url_column=args.url_column,
            label_column=args.label_column,
            label_map={args.positive: 1, args.negative: 0},
        )
    elif args.command.startswith("registry-"):
        from phishguard.ml.registry import LocalRegistry, QualityGate

        registry = LocalRegistry(args.root)
        if args.command == "registry-register":
            result = registry.register(args.model, args.report)
        elif args.command == "registry-activate":
            gate = QualityGate(
                args.min_precision, args.min_recall, args.max_fpr, args.min_test_rows
            )
            result = registry.activate(args.version, gate)
        else:
            result = registry.list()
    elif args.command in {"spark-stream", "analytics", "images-etl"}:
        from phishguard.processing.spark_session import create_spark

        spark = create_spark(kafka=args.command == "spark-stream")
        query = None
        try:
            if args.command == "images-etl":
                from phishguard.processing.image_etl import image_etl

                result = image_etl(spark, args.legitimate_root, args.phishing_root, args.output)
            elif args.command == "analytics":
                from phishguard.analytics.spark_analytics import aggregate

                frame = aggregate(spark, args.input, args.output)
                result = {"aggregate_rows": frame.count()}
            else:
                from phishguard.streaming.stream_predict import start_stream

                query = start_stream(
                    spark,
                    args.model,
                    args.bootstrap,
                    args.output,
                    args.checkpoint,
                    available_now=args.available_now,
                )
                query.awaitTermination()
                result = {"query_id": str(query.id), "recent_progress": query.recentProgress}
        except KeyboardInterrupt:
            result = {"stopped": True}
        finally:
            if query is not None and query.isActive:
                query.stop()
            spark.stop()
    elif args.command == "predict":
        from phishguard.ml.model_registry import URLModel

        result = URLModel.load(args.model).predict(args.url)
    elif args.command == "publish":
        from phishguard.streaming.kafka_producer import producer, publish_url

        result = {"event_id": publish_url(producer(), args.url)}
    elif args.command == "consume":
        import signal
        import threading
        from phishguard.streaming.kafka_consumer import consume

        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        result = {"processed": consume(args.model, stop=stop)}
    elif args.command == "topics":
        from confluent_kafka.admin import AdminClient, NewTopic
        from confluent_kafka import KafkaException, KafkaError
        from phishguard.streaming.kafka_producer import kafka_config

        admin = AdminClient(kafka_config())
        futures = admin.create_topics(
            [
                NewTopic(
                    "phishguard." + name,
                    num_partitions=3,
                    replication_factor=1,
                    config={"retention.ms": "3600000"},
                )
                for name in ("raw_urls", "predictions", "dead_letter")
            ]
        )
        for future in futures.values():
            try:
                future.result(30)
            except KafkaException as exc:
                if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
        result = {"topics": list(futures)}
    elif args.command == "inventory":
        from phishguard.ingestion.verify_dataset import inventory

        for record in inventory(args.root, args.hash):
            print(json.dumps(record))
        return
    else:
        from phishguard.ml.vision import train_vision

        result = train_vision(
            args.root,
            args.output,
            args.epochs,
            manifest=args.manifest,
            batch_size=args.batch_size,
            device=args.device,
            cache_dir=args.cache_dir,
            architecture_variant=args.architecture,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
