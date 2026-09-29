# Gold: analysis-ready tables consumed by the API dashboard and the agent's metric tools.
import dlt
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

PRIORITY_LABEL = F.expr(
    "CASE priority WHEN 1 THEN '1 - Critical' WHEN 2 THEN '2 - High' WHEN 3 THEN '3 - Moderate' "
    "WHEN 4 THEN '4 - Low' WHEN 5 THEN '5 - Planning' END"
)
SLA_TARGET_HOURS = F.expr(
    "CASE priority WHEN 1 THEN 4 WHEN 2 THEN 8 WHEN 3 THEN 72 WHEN 4 THEN 120 WHEN 5 THEN 240 END"
)

SPIKE_MIN_COUNT = 10
SPIKE_RATIO = 3.0


@dlt.table(comment="One row per incident with derived resolution and SLA fields.")
def gold_incident_facts() -> DataFrame:
    kb_ref = F.regexp_extract("close_notes", r"(KB\d{7})", 1)
    return (
        dlt.read("silver_incidents")
        .withColumn("priority_label", PRIORITY_LABEL)
        .withColumn("sla_target_hours", SLA_TARGET_HOURS)
        .withColumn("is_resolved", F.col("resolved_at").isNotNull())
        .withColumn(
            "mttr_hours",
            (F.unix_timestamp("resolved_at") - F.unix_timestamp("opened_at")) / 3600.0,
        )
        .withColumn("sla_breached", ~F.col("made_sla"))
        .withColumn("was_reassigned", F.col("reassignment_count") > 0)
        .withColumn("opened_date", F.to_date("opened_at"))
        .withColumn("opened_week", F.date_trunc("week", "opened_at").cast("date"))
        .withColumn("kb_reference", F.when(kb_ref == "", None).otherwise(kb_ref))
    )


@dlt.table(comment="Daily incident volume, resolution time and SLA by group/category/priority.")
def gold_daily_metrics() -> DataFrame:
    return (
        dlt.read("gold_incident_facts")
        .groupBy("opened_date", "assignment_group", "category", "priority_label", "location")
        .agg(
            F.count("*").alias("incidents_opened"),
            F.sum(F.col("is_resolved").cast("int")).alias("incidents_resolved"),
            F.avg("mttr_hours").alias("avg_mttr_hours"),
            F.percentile_approx("mttr_hours", 0.9).alias("p90_mttr_hours"),
            F.sum(F.col("sla_breached").cast("int")).alias("sla_breaches"),
            F.sum(F.col("was_reassigned").cast("int")).alias("reassigned"),
        )
    )


@dlt.table(comment="Weekly volume per site+subcategory vs trailing 4-week average; flags spikes.")
def gold_hotspots() -> DataFrame:
    weekly = (
        dlt.read("gold_incident_facts")
        .groupBy("opened_week", "location", "category", "subcategory")
        .agg(
            F.count("*").alias("incidents"),
            F.min("priority_label").alias("worst_priority_label"),
        )
    )
    trailing = (
        Window.partitionBy("location", "category", "subcategory")
        .orderBy("opened_week")
        .rowsBetween(-4, -1)
    )
    # Weeks with zero incidents have no row, so the trailing average skews high. That makes
    # spike detection conservative, which is acceptable for a hotspot view.
    return (
        weekly.withColumn("trailing_4wk_avg", F.coalesce(F.avg("incidents").over(trailing), F.lit(0.0)))
        .withColumn(
            "spike_ratio",
            F.col("incidents") / F.greatest(F.col("trailing_4wk_avg"), F.lit(1.0)),
        )
        .withColumn(
            "is_spike",
            (F.col("incidents") >= SPIKE_MIN_COUNT) & (F.col("spike_ratio") >= SPIKE_RATIO),
        )
    )
