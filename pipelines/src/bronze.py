# Bronze: raw ServiceNow-shaped extracts, ingested incrementally with Auto Loader.
# Every column lands as a string; typing and cleanup happen in silver.
import dlt
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

RAW_PATH = spark.conf.get("raw_path")  # noqa: F821 - `spark` is provided by the pipeline runtime


def _autoload(folder: str) -> DataFrame:
    return (
        spark.readStream.format("cloudFiles")  # noqa: F821
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "false")
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .load(f"{RAW_PATH}/{folder}/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )


@dlt.table(comment="Raw incident extracts, append-only.")
def bronze_incidents() -> DataFrame:
    return _autoload("incidents")


@dlt.table(comment="Raw knowledge article extracts, append-only.")
def bronze_kb_articles() -> DataFrame:
    return _autoload("kb_articles")
