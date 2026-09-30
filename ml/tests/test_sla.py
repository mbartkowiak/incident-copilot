import pandas as pd

from sla.evaluate import breach_by_routing, evaluate
from sla.model import breach_rate_lookup, intake_features


def _incidents(n_weeks: int = 20) -> pd.DataFrame:
    rows = []
    for week in range(n_weeks):
        opened = pd.Timestamp("2026-05-04 09:00") + pd.Timedelta(weeks=week)
        for i in range(10):
            slow = i < 4  # SAP tickets breach, VPN tickets don't
            rows.append(
                {
                    "number": f"INC{week:03d}{i}",
                    "opened_at": opened + pd.Timedelta(hours=i),
                    "short_description": "SAP month-end slow" if slow else "VPN drops",
                    "description": "",
                    "priority": 2 if i < 7 else 4,
                    "category": "software" if slow else "network",
                    "subcategory": "sap" if slow else "vpn",
                    "location": "Chicago HQ",
                    "contact_type": "phone",
                    "was_reassigned": i in (0, 1),
                    "sla_breached": slow,
                }
            )
    return pd.DataFrame(rows)


def test_intake_features_use_only_fields_known_at_open() -> None:
    features = intake_features(_incidents(1))

    assert "sla_breached" not in features
    assert "was_reassigned" not in features
    assert features.loc[0, "text"] == "SAP month-end slow\n"
    assert features.loc[0, "priority"] == "2"
    assert features.loc[0, "opened_weekday"] == "weekday"


def test_lookup_smooths_toward_the_priority_rate_and_falls_back_for_unseen_groups() -> None:
    train = pd.DataFrame(
        {
            "subcategory": ["sap"] * 5 + ["vpn"] * 5,
            "priority": [2] * 10,
            "sla_breached": [True] * 5 + [False] * 5,
        }
    )
    score = pd.DataFrame({"subcategory": ["sap", "email"], "priority": [2, 2]})

    rates = breach_rate_lookup(train, score)

    assert rates[0] == (5 + 5 * 0.5) / (5 + 5)  # pulled from 100% toward the P2 rate of 50%
    assert rates[1] == 0.5  # never seen: the P2 rate


def test_evaluate_reports_every_estimator_on_all_and_urgent_tickets() -> None:
    report = evaluate(_incidents(), "2026-08-01")

    assert set(report["p1_p2_only"]) == {
        "priority_only",
        "subcategory_priority_lookup",
        "logistic_regression",
    }
    assert report["p1_p2_only"]["subcategory_priority_lookup"]["roc_auc"] == 1.0
    assert report["train_rows"] + report["test_rows"] == 200


def test_breach_by_routing_splits_urgent_tickets_by_reassignment() -> None:
    result = breach_by_routing(_incidents(2))

    assert result["misrouted"] == {"breach_rate": 1.0, "tickets": 4}
    assert result["routed_right"]["tickets"] == 10
