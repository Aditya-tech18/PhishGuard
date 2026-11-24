"""Spark construction kept out of imports to permit lightweight API deployment."""

import os


def create_spark(master="local[2]", kafka=False):
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.appName("PhishGuard2")
        .master(master)
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.driver.memory", os.getenv("PHISHGUARD_SPARK_DRIVER_MEMORY", "2g"))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.adaptive.enabled", "true")
    )
    if os.getenv("PHISHGUARD_SPARK_IVY"):
        builder = builder.config("spark.jars.ivy", os.environ["PHISHGUARD_SPARK_IVY"])
    if kafka:
        builder = builder.config(
            "spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.8"
        )
    # Explicit override for constrained test machines, never hard-code a cluster address.
    if os.getenv("PHISHGUARD_SPARK_LOCAL_IP"):
        builder = builder.config("spark.driver.host", os.environ["PHISHGUARD_SPARK_LOCAL_IP"])
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
