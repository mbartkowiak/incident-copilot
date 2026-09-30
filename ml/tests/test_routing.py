import pandas as pd

from routing.data import time_split
from routing.llm import PRICES, LlmPrediction, cost_per_1k
from routing.model import build_pipeline


def test_time_split_trains_on_past_and_tests_on_future() -> None:
    df = pd.DataFrame(
        {"opened_at": pd.to_datetime(["2026-06-30 23:59", "2026-07-01 00:00", "2026-08-15 09:30"])}
    )

    train, test = time_split(df, "2026-07-01")

    assert len(train) == 1
    assert len(test) == 2
    assert train["opened_at"].max() < test["opened_at"].min()


def test_pipeline_learns_separable_text_and_exposes_probabilities() -> None:
    texts = ["vpn gateway not responding"] * 6 + ["printer offline paper jam"] * 6
    labels = ["Network Operations"] * 6 + ["End User Computing"] * 6
    pipe = build_pipeline()
    pipe.fit(pd.DataFrame({"text": texts}), labels)

    probe = pd.DataFrame({"text": ["gateway vpn keeps failing", "printer jam again"]})

    assert list(pipe.predict(probe)) == ["Network Operations", "End User Computing"]
    assert pipe.predict_proba(probe).shape == (2, 2)


def test_cost_per_1k_uses_input_and_output_prices() -> None:
    preds = [LlmPrediction("x", 1.0, input_tokens=1000, output_tokens=100)] * 2
    price_in, price_out = PRICES["claude-haiku-4-5"]

    expected = (1000 * price_in + 100 * price_out) / 1e6 * 1000
    assert abs(cost_per_1k("claude-haiku-4-5", preds) - expected) < 1e-9
