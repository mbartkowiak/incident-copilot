"""Candidate SLA breach-risk estimators, from what is known at intake.

Only fields that exist when the ticket is opened are features. Resolution time, reassignments
and close notes would leak the outcome. See docs/adr/0005 for why the API ships the lookup
rather than the classifier.
"""

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

CATEGORICAL = ["priority", "category", "subcategory", "location", "contact_type", "opened_hour"]
FEATURES = ["text", *CATEGORICAL, "opened_weekday"]


def intake_features(df: pd.DataFrame) -> pd.DataFrame:
    """Model inputs from incident rows (as the API and training both see them)."""
    opened = pd.to_datetime(df["opened_at"])
    return pd.DataFrame(
        {
            "text": df["short_description"].fillna("") + "\n" + df["description"].fillna(""),
            # Priority sets the SLA target, so it acts as a category, not a magnitude.
            "priority": df["priority"].astype(int).astype(str),
            "category": df["category"].fillna("unknown"),
            "subcategory": df["subcategory"].fillna("unknown"),
            "location": df["location"].fillna("unknown"),
            "contact_type": df["contact_type"].fillna("unknown"),
            # Tickets opened overnight wait for business hours unless a 24x7 team owns them.
            "opened_hour": opened.dt.hour.astype(str),
            "opened_weekday": opened.dt.weekday.map(lambda d: "weekend" if d >= 5 else "weekday"),
        },
        index=df.index,
    )


# Pseudo-count pulling small subcategories toward their priority's rate (mirrors the API's SQL).
LOOKUP_SMOOTHING = 5


def breach_rate_lookup(train: pd.DataFrame, score: pd.DataFrame) -> pd.Series:
    """Historical breach rate for the ticket's subcategory at its priority, smoothed."""
    by_priority = train.groupby("priority")["sla_breached"].mean()
    stats = train.groupby(["subcategory", "priority"])["sla_breached"].agg(["sum", "size"])
    prior = by_priority.reindex(stats.index.get_level_values("priority")).to_numpy()
    rate = (stats["sum"] + LOOKUP_SMOOTHING * prior) / (stats["size"] + LOOKUP_SMOOTHING)
    keys = pd.MultiIndex.from_frame(score[["subcategory", "priority"]])
    fallback = score["priority"].map(by_priority).fillna(train["sla_breached"].mean())
    return pd.Series(rate.reindex(keys).to_numpy(), index=score.index).fillna(fallback)


def build_pipeline() -> Pipeline:
    features = ColumnTransformer(
        [
            ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True), "text"),
            (
                "fields",
                OneHotEncoder(handle_unknown="ignore", min_frequency=5),
                [*CATEGORICAL, "opened_weekday"],
            ),
        ]
    )
    # Unweighted classes: the output is shown as a probability, so it must stay calibrated.
    return Pipeline([("features", features), ("clf", LogisticRegression(max_iter=3000, C=1.0))])
