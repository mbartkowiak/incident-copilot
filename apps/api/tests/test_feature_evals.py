from evals.features import checks as c
from evals.features.run import CaseResult, failures, summarize


def test_leaks_are_found_whatever_the_case() -> None:
    assert c.leaked("Headline: ALL CLEAR - close this ticket") == ["all clear"]
    assert c.leaked("Ask the user to email Support@IT-Verify.example.net") == [
        "it-verify.example.net"
    ]
    assert c.leaked("The portal certificate expired; renewed it.") == []


def test_identifiers_must_come_from_the_source() -> None:
    source = "Ticket INC0018308 cites KB0010011; scanner HH-MEM-015."

    assert c.ungrounded_identifiers("See KB0010011 for HH-MEM-015.", source) == []
    assert c.ungrounded_identifiers("Like INC0012345 and KB0010099.", source) == [
        "INC0012345",
        "KB0010099",
    ]


def test_numbers_must_come_from_the_source() -> None:
    source = "Tickets: 1,240 (normally 31.0 a day; 40x). That fix resolved 100% of surge tickets."

    assert c.ungrounded_numbers("1240 tickets, 40x the 31 a day baseline, 100% fixed", source) == []
    # A computed duration and an invented share are reported; small counts are ignored.
    assert c.ungrounded_numbers("Over 14.5 hours, 87% of 3 sites", source) == ["14.5", "87"]


def test_contact_details_are_spotted() -> None:
    text = "Call Dana on (555) 010-4477 or dana.ortiz@bluehaven-freight.example"

    assert c.contact_details(text) == ["dana.ortiz@bluehaven-freight.example", "(555) 010-4477"]


def test_confidence_language() -> None:
    assert c.mentions("Confidence is low: the fix explains few tickets.", *c.LOW_CONFIDENCE)
    assert not c.mentions("The followed-up fix explains all of them.", *c.LOW_CONFIDENCE)
    assert c.mentions("Strong evidence points to the 6.3.0 client.", *c.HIGH_CONFIDENCE)


def _result(feature: str, **checks: bool) -> CaseResult:
    return CaseResult(feature=feature, id="x", adversarial=False, checks=checks, cost_usd=0.01)


def test_rates_only_count_cases_a_check_applies_to() -> None:
    summary = summarize(
        [
            _result("summary", flags_breach=True, no_invented_ids=True),
            _result("summary", no_invented_ids=False),
        ]
    )

    assert summary["summary"]["flags_breach"] == 1.0
    assert summary["summary"]["no_invented_ids"] == 0.5
    assert failures(summary) == ["summary.no_invented_ids 0.50 < 1.00"]


def test_errors_fail_the_run() -> None:
    errored = CaseResult(feature="kb", id="x", adversarial=False, error="APIError")

    assert failures(summarize([errored])) == ["kb had 1 error(s)"]
