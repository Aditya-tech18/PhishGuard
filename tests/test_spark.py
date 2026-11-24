import pytest
from phishguard.features.url_features import vector

pytestmark = pytest.mark.spark


def test_etl_feature_parity_and_rejects(tmp_path):
    pytest.importorskip("pyspark")
    from phishguard.processing.spark_session import create_spark
    from phishguard.processing.write_parquet import batch_etl

    source = tmp_path / "input.csv"
    source.write_text(
        "url,label\nhttps://example.com/about,0\nhttps://example.com/about,0\n"
        "http://verify-account.test/login,1\nfile:///secret,1\n"
    )
    spark = create_spark()
    try:
        output = tmp_path / "run"
        result = batch_etl(spark, source, output)
        assert result["accepted_unique"] == 2
        frame = spark.read.parquet(str(output / "gold"))
        for row in frame.collect():
            assert row.features == vector(row.url)
        rejected = spark.read.json(str(output / "reject_summary")).collect()
        assert rejected[0]["error"] == "invalid_url"
        assert rejected[0]["count"] == 1
        with pytest.raises(ValueError):
            batch_etl(spark, source, output)
    finally:
        spark.stop()


def test_image_metadata_no_pixels_and_boolean_partitions(tmp_path):
    pytest.importorskip("pyspark")
    pytest.importorskip("PIL")
    from PIL import Image
    from phishguard.processing.spark_session import create_spark
    from phishguard.processing.image_etl import image_etl

    legitimate, phishing = tmp_path / "legitimate", tmp_path / "phishing"
    legitimate.mkdir()
    phishing.mkdir()
    Image.new("RGB", (32, 32), "blue").save(legitimate / "good.png")
    (phishing / "duplicate.png").write_bytes((legitimate / "good.png").read_bytes())
    (phishing / "invalid.png").write_bytes(b"not an image")
    spark = create_spark()
    try:
        result = image_etl(spark, legitimate, phishing, tmp_path / "image-output")
        assert result["files"] == 3
        assert result["valid_files"] == 2
        assert result["invalid_files"] == 1
        assert result["duplicate_groups"] == 1
        frame = spark.read.parquet(str(tmp_path / "image-output/metadata"))
        assert "content" not in frame.columns and "path" not in frame.columns
        assert sum(row["bytes"] for row in frame.collect()) == result["bytes"]
    finally:
        spark.stop()
