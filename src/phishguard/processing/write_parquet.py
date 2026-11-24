"""Batch ETL writes new run directories only; never overwrites raw data."""

from pathlib import Path
from phishguard.processing.clean_urls import clean_frame
from phishguard.processing.build_features import build_features


def batch_etl(
    spark,
    source,
    output,
    delimiter=",",
    url_column="url",
    label_column="label",
    positive="1",
    negative="0",
):
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists() or output == source or source in output.parents:
        raise ValueError("Output must be a new path outside the input")
    if not source.is_file():
        raise ValueError("Input must be an explicit CSV file")
    # Persist bronze only when explicitly running ETL: it contains sensitive URLs.
    frame = (
        spark.read.option("header", True)
        .option("sep", delimiter)
        .option("mode", "FAILFAST")
        .csv(str(source))
    )
    good, rejected = clean_frame(frame, url_column, label_column, positive, negative)
    features = build_features(good).cache()
    try:
        rows = features.count()
        features.write.mode("errorifexists").parquet(str(output / "gold"))
        rejected.write.mode("errorifexists").json(str(output / "reject_summary"))
        features.groupBy("label").count().write.mode("errorifexists").json(
            str(output / "label_counts")
        )
        return {"accepted_unique": rows, "output": str(output)}
    finally:
        features.unpersist()
