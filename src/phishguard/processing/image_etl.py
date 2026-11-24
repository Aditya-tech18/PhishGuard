"""Distributed, bounded image metadata ETL over explicit legitimate/phishing roots.

Raw pixels never appear in the output. Header/format verification and checksums happen on
Spark workers. This does not train a classifier or infer site-isolation from filenames.
"""

import hashlib
import io
import warnings
from phishguard.common.files import reject_symlink_chain


def inspect_bytes(content, max_bytes=5_000_000):
    from PIL import Image

    if not content or len(content) > max_bytes:
        return False, None, None, None, None, "invalid_byte_size"
    try:
        data = bytes(content)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    return False, None, None, None, None, "unsupported_format"
                width, height = image.size
                if not 1 <= width * height <= 16_000_000:
                    return False, None, None, None, None, "pixel_limit"
                image_format = image.format
                image.verify()
        return True, width, height, image_format, hashlib.sha256(data).hexdigest(), None
    except (
        OSError,
        ValueError,
        SyntaxError,
        OverflowError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        return False, None, None, None, None, "invalid_image"


def checked_root(root):
    root = reject_symlink_chain(root)
    if not root.is_dir():
        raise ValueError("Image root must be a directory")
    # Inventory is read-only. Reject symlink descendants before Spark's recursive reader runs.
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Image source contains symlinks")
    return root.resolve()


def metadata_frame(spark, root, label, max_bytes=5_000_000):
    from pyspark.sql import functions as F, types as T

    if label not in {0, 1} or not 1 <= max_bytes <= 5_000_000:
        raise ValueError("Explicit binary label and bounded image size required")
    root = checked_root(root)
    schema = T.StructType(
        [
            T.StructField("valid", T.BooleanType(), False),
            T.StructField("width", T.IntegerType()),
            T.StructField("height", T.IntegerType()),
            T.StructField("format", T.StringType()),
            T.StructField("image_sha256", T.StringType()),
            T.StructField("error", T.StringType()),
        ]
    )
    source = spark.read.format("binaryFile").option("recursiveFileLookup", "true").load(str(root))
    base_columns = [
        F.sha2("path", 256).alias("file_id"),
        F.col("length").alias("bytes"),
        F.lit(label).alias("label"),
    ]
    valid_size = source.where((F.col("length") > 0) & (F.col("length") <= max_bytes))
    # Binary rows are large. Standard scalar Python UDF batching can serialize hundreds of
    # images together and exhaust a small JVM heap. Bound Arrow batches to four images.
    spark.conf.set("spark.sql.execution.arrow.maxRecordsPerBatch", "4")
    output_schema = T.StructType(
        [
            T.StructField("file_id", T.StringType()),
            T.StructField("bytes", T.LongType()),
            T.StructField("label", T.IntegerType()),
            *schema.fields,
        ]
    )

    def inspect_batches(batches):
        import pandas as pd

        names = [field.name for field in output_schema.fields]
        for batch in batches:
            rows = []
            for row in batch.itertuples(index=False):
                rows.append(
                    (row.file_id, row.bytes, row.label, *inspect_bytes(row.content, max_bytes))
                )
            yield pd.DataFrame(rows, columns=names)

    inspected = valid_size.select(*base_columns, "content").mapInPandas(
        inspect_batches, output_schema
    )
    oversized = source.where((F.col("length") <= 0) | (F.col("length") > max_bytes)).select(
        *base_columns,
        F.lit(False).alias("valid"),
        F.lit(None).cast("int").alias("width"),
        F.lit(None).cast("int").alias("height"),
        F.lit(None).cast("string").alias("format"),
        F.lit(None).cast("string").alias("image_sha256"),
        F.lit("invalid_byte_size").alias("error"),
    )
    return inspected.unionByName(oversized)


def image_etl(spark, legitimate_root, phishing_root, output):
    from pyspark.sql import functions as F

    legitimate_root, phishing_root = checked_root(legitimate_root), checked_root(phishing_root)
    if (
        legitimate_root == phishing_root
        or legitimate_root in phishing_root.parents
        or phishing_root in legitimate_root.parents
    ):
        raise ValueError("Class roots must be separate, non-nested trees")
    output = reject_symlink_chain(output)
    if output.exists() or any(
        root == output or root in output.parents or output in root.parents
        for root in [legitimate_root, phishing_root]
    ):
        raise ValueError("Output must be a fresh directory outside both source trees")
    frame = metadata_frame(spark, legitimate_root, 0).unionByName(
        metadata_frame(spark, phishing_root, 1)
    )
    # Parquet becomes the materialized boundary, avoiding repeated full-image reads for summaries.
    frame.write.mode("errorifexists").partitionBy("label", "valid").parquet(
        str(output / "metadata")
    )
    saved = spark.read.parquet(str(output / "metadata"))
    quality = saved.groupBy("label", "valid", "error").agg(
        F.count("*").alias("files"), F.sum("bytes").alias("bytes")
    )
    quality.write.mode("errorifexists").json(str(output / "quality"))
    duplicate_groups = (
        saved.where("valid = true")
        .groupBy("image_sha256")
        .agg(F.count("*").alias("files"), F.countDistinct("label").alias("distinct_labels"))
        .where("files > 1")
    )
    duplicate_groups.write.mode("errorifexists").parquet(str(output / "duplicate_groups"))
    totals = (
        saved.agg(
            F.count("*").alias("files"),
            F.sum("bytes").alias("bytes"),
            F.coalesce(F.sum(F.col("valid").cast("boolean").cast("int")), F.lit(0)).alias(
                "valid_files"
            ),
        )
        .first()
        .asDict()
    )
    return {
        **totals,
        "invalid_files": totals["files"] - totals["valid_files"],
        "duplicate_groups": duplicate_groups.count(),
        "output_contains_pixels": False,
        "verification": "PNG/JPEG structural verification and bounded dimensions; not visual label verification",
    }
