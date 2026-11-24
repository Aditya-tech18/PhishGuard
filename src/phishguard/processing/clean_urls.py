"""A single UDF normalization contract, including error classification, for Spark ETL."""

from phishguard.features.url_features import normalize_url


def normalize_record(url, label, positive="1", negative="0"):
    if positive == negative:
        raise ValueError("Positive and negative labels must differ")
    try:
        cleaned = normalize_url(url.strip())
    except (ValueError, AttributeError, TypeError):
        return None, None, "invalid_url"
    raw_label = str(label).strip()
    if raw_label not in {positive, negative}:
        return None, None, "invalid_label"
    return cleaned, int(raw_label == positive), None


def clean_frame(frame, url_column="url", label_column="label", positive="1", negative="0"):
    from pyspark.sql import functions as F, types as T

    if not {url_column, label_column} <= set(frame.columns):
        raise ValueError("URL/label columns not found; specify the correct columns")
    if positive == negative:
        raise ValueError("Label polarity is ambiguous")
    schema = T.StructType(
        [
            T.StructField("url", T.StringType()),
            T.StructField("label", T.IntegerType()),
            T.StructField("error", T.StringType()),
        ]
    )
    normalize = F.udf(lambda u, label: normalize_record(u, label, positive, negative), schema)
    clean = frame.select(normalize(F.col(url_column), F.col(label_column)).alias("row")).select(
        "row.*"
    )
    rejected = clean.where(F.col("error").isNotNull()).groupBy("error").count()
    good = clean.where(F.col("error").isNull()).drop("error")
    conflicts = (
        good.groupBy("url").agg(F.countDistinct("label").alias("labels")).where("labels > 1")
    )
    if conflicts.limit(1).count():
        raise ValueError("Conflicting labels found for normalized URLs")
    return good.dropDuplicates(["url"]), rejected
