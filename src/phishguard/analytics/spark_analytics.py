"""Distributed aggregate reports over minimized prediction Parquet."""


def aggregate(spark, source, output):
    from pyspark.sql import functions as F

    frame = spark.read.parquet(str(source))
    valid = frame.where("error IS NULL").dropDuplicates(["event_id"])
    daily = valid.groupBy(F.to_date("timestamp").alias("date"), "verdict", "model_version").count()
    daily.write.mode("errorifexists").parquet(str(output))
    return daily
