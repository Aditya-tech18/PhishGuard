"""Spark features use the same pure function as the live model, never input feature columns."""

from phishguard.features.feature_schema import FEATURE_NAMES
from phishguard.features.url_features import vector


def build_features(frame):
    from pyspark.sql import functions as F, types as T

    extract = F.udf(vector, T.ArrayType(T.DoubleType(), containsNull=False))
    result = frame.withColumn("features", extract("url"))
    for i, name in enumerate(FEATURE_NAMES):
        result = result.withColumn(name, F.col("features")[i])
    return result
