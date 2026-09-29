import re
from collections import Counter
from datetime import datetime

import pytest

from datagen import Dataset, generate, load_archetypes
from datagen import reference as ref
from datagen.generator import TS_FORMAT


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return generate(count=3000, seed=7)


def _ts(value: str) -> datetime:
    return datetime.strptime(value, TS_FORMAT)


def test_archetype_catalog_is_valid() -> None:
    archetypes = load_archetypes()
    assert len(archetypes) >= 25
    assert {a.group for a in archetypes} == set(ref.GROUPS)


def test_same_seed_is_deterministic() -> None:
    a = generate(count=300, seed=1)
    b = generate(count=300, seed=1)
    c = generate(count=300, seed=2)
    assert a.incidents == b.incidents
    assert a.kb_articles == b.kb_articles
    assert a.incidents != c.incidents


def test_counts_include_bursts(ds: Dataset) -> None:
    burst_total = sum(b.count for b in ref.BURSTS)
    assert len(ds.ground_truth) == 3000 + burst_total
    duplicates = sum("duplicate_row" in g["defects"] for g in ds.ground_truth)
    assert len(ds.incidents) == len(ds.ground_truth) + duplicates


def test_numbers_are_unique_and_ordered(ds: Dataset) -> None:
    numbers = [g["number"] for g in ds.ground_truth]
    assert len(set(numbers)) == len(numbers)
    assert numbers == sorted(numbers)
    assert all(re.fullmatch(r"INC\d{7}", n) for n in numbers)


def test_priority_follows_servicenow_matrix(ds: Dataset) -> None:
    for inc in ds.incidents:
        assert inc["priority"] == ref.PRIORITY_MATRIX[(inc["impact"], inc["urgency"])]


def test_no_unfilled_template_slots(ds: Dataset) -> None:
    fields = ("short_description", "description", "close_notes", "cmdb_ci")
    for inc in ds.incidents:
        for f in fields:
            assert "{" not in (inc[f] or ""), (inc["number"], f, inc[f])


def test_timestamps_consistent_except_injected_defects(ds: Dataset) -> None:
    defects = {g["number"]: g["defects"] for g in ds.ground_truth}
    for inc in ds.incidents:
        if inc["resolved_at"] is None:
            assert inc["state"] in {"New", "In Progress", "On Hold"}
            continue
        if "resolved_before_opened" in defects[inc["number"]]:
            assert _ts(inc["resolved_at"]) < _ts(inc["opened_at"])
        else:
            assert _ts(inc["resolved_at"]) >= _ts(inc["opened_at"])
        if inc["closed_at"]:
            assert inc["state"] == "Closed"


def test_resolved_incidents_land_in_true_group(ds: Dataset) -> None:
    truth = {g["number"]: g for g in ds.ground_truth}
    for inc in ds.incidents:
        if inc["resolved_at"]:
            assert inc["assignment_group"] == truth[inc["number"]]["true_assignment_group"]
            misrouted = truth[inc["number"]]["initial_assignment_group"] != inc["assignment_group"]
            assert (inc["reassignment_count"] > 0) == misrouted


def test_misrouting_is_meaningful(ds: Dataset) -> None:
    misrouted = sum(
        g["initial_assignment_group"] != g["true_assignment_group"] for g in ds.ground_truth
    )
    assert 0.10 < misrouted / len(ds.ground_truth) < 0.35


def test_kb_references_resolve(ds: Dataset) -> None:
    kb_numbers = {kb["number"] for kb in ds.kb_articles}
    refs = [m for inc in ds.incidents for m in re.findall(r"KB\d{7}", inc["close_notes"] or "")]
    assert refs
    assert set(refs) <= kb_numbers


def test_chicago_outage_is_visible(ds: Dataset) -> None:
    per_day = Counter(
        inc["opened_at"][:10]
        for inc in ds.incidents
        if inc["location"] == "Chicago HQ" and inc["subcategory"] == "lan"
    )
    assert per_day["2026-03-10"] >= 80
    assert max(n for d, n in per_day.items() if d != "2026-03-10") < 10


def test_vpn_upgrade_window_raises_volume(ds: Dataset) -> None:
    vpn = [inc for inc in ds.incidents if inc["subcategory"] == "vpn"]
    in_window = sum("2026-05-04" <= i["opened_at"][:10] <= "2026-06-15" for i in vpn)
    # the 6-week window is ~12% of the year; with a 4x multiplier it holds far more than that
    assert in_window / len(vpn) > 0.3


def test_pii_is_injected_and_tracked(ds: Dataset) -> None:
    pii_numbers = {g["number"] for g in ds.ground_truth if g["has_pii"]}
    assert 0.03 < len(pii_numbers) / len(ds.ground_truth) < 0.10
    sample = next(i for i in ds.incidents if i["number"] in pii_numbers)
    assert "555-01" in sample["description"] or ref.COMPANY_DOMAIN in sample["description"]
