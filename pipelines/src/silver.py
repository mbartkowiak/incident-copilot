# Silver: typed, deduplicated, PII-scrubbed records with data-quality expectations.
import dlt
from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

TS = "yyyy-MM-dd HH:mm:ss"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PHONE_RE = r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}"


def _scrub(col: str) -> Column:
    return F.regexp_replace(F.regexp_replace(F.col(col), EMAIL_RE, "[EMAIL]"), PHONE_RE, "[PHONE]")


def _blank_to_null(col: str) -> Column:
    trimmed = F.trim(F.col(col))
    return F.when(trimmed == "", None).otherwise(trimmed)


def _latest_per_key(df: DataFrame, key: str) -> DataFrame:
    w = Window.partitionBy(key).orderBy(F.col("sys_updated_on").desc(), F.col("_ingested_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")


@dlt.table(comment="Cleaned incidents: typed, one row per number, PII scrubbed.")
@dlt.expect_or_drop("has_number", "number IS NOT NULL")
@dlt.expect_or_drop("has_short_description", "short_description IS NOT NULL")
@dlt.expect_or_drop("resolved_after_opened", "resolved_at IS NULL OR resolved_at >= opened_at")
@dlt.expect("priority_in_range", "priority BETWEEN 1 AND 5")
@dlt.expect("resolved_has_group", "resolved_at IS NULL OR assignment_group IS NOT NULL")
def silver_incidents() -> DataFrame:
    typed = dlt.read("bronze_incidents").select(
        F.col("number"),
        F.col("sys_id"),
        F.to_timestamp("opened_at", TS).alias("opened_at"),
        F.to_timestamp("resolved_at", TS).alias("resolved_at"),
        F.to_timestamp("closed_at", TS).alias("closed_at"),
        F.to_timestamp("sys_updated_on", TS).alias("sys_updated_on"),
        F.col("state"),
        F.col("impact").cast("int").alias("impact"),
        F.col("urgency").cast("int").alias("urgency"),
        F.col("priority").cast("int").alias("priority"),
        F.col("category"),
        F.col("subcategory"),
        F.col("cmdb_ci"),
        F.col("location"),
        F.col("contact_type"),
        F.col("caller_id"),
        F.col("assignment_group"),
        F.col("assigned_to"),
        F.col("reassignment_count").cast("int").alias("reassignment_count"),
        F.col("reopen_count").cast("int").alias("reopen_count"),
        F.col("made_sla").cast("boolean").alias("made_sla"),
        F.col("close_code"),
        _blank_to_null("short_description").alias("short_description"),
        _scrub("description").alias("description"),
        _scrub("close_notes").alias("close_notes"),
        _scrub("work_notes").alias("work_notes"),
        F.col("_ingested_at"),
    )
    return _latest_per_key(typed, "number")


@dlt.table(comment="Published knowledge articles, one row per number.")
@dlt.expect_or_drop("has_number", "number IS NOT NULL")
@dlt.expect_or_drop("has_text", "text IS NOT NULL")
def silver_kb_articles() -> DataFrame:
    typed = (
        dlt.read("bronze_kb_articles")
        .filter(F.col("workflow_state") == "published")
        .select(
            "number",
            F.col("short_description").alias("title"),
            "text",
            "kb_category",
            "category",
            "subcategory",
            "author",
            F.to_timestamp("published", TS).alias("published_at"),
            F.to_timestamp("sys_updated_on", TS).alias("sys_updated_on"),
            "_ingested_at",
        )
    )
    return _latest_per_key(typed, "number")
