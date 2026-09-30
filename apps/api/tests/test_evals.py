from evals.run import CaseResult, failures, summarize


def _case(vague: bool, correct: bool = True, questions: bool = False) -> CaseResult:
    return CaseResult(
        id="INC1",
        is_vague=vague,
        true_group="Service Desk",
        predicted_group="Service Desk" if correct else "Cloud Platform",
        team_correct=correct,
        grounded=True,
        cited_expected_kb=True,
        asked_questions=questions,
        error=None,
        cost_usd=0.05,
        latency_s=10.0,
        turns=2,
    )


def test_summary_splits_clear_and_vague() -> None:
    summary = summarize([_case(False), _case(False, correct=False), _case(True, questions=True)])

    assert summary["team_accuracy_clear"] == 0.5
    assert summary["questions_on_vague_rate"] == 1.0
    assert failures(summary) == ["team_accuracy_clear 0.50 < 0.90"]


def test_untested_categories_do_not_fail_a_filtered_run() -> None:
    summary = summarize([_case(False)])

    assert summary["questions_on_vague_rate"] is None
    assert failures(summary) == []
