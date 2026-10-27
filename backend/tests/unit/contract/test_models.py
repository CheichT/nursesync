"""Tests that the handoff formats match the PRD: good data passes, bad data is rejected.

Owner: Cheich (formats), reviewed by Kerrian.
"""

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contract.models import (
    Assignment,
    AvailabilityRow,
    Callout,
    CheckRulesResult,
    DemandRow,
    Draft,
    Nurse,
    OpenGap,
    RulesConfig,
    SoftTradeoff,
    Suggestion,
    Unfixable,
    Violation,
)

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"


def load(name):
    return json.loads((MOCK / name).read_text())


# --- the mock data fits the forms --------------------------------------------------


def test_mock_roster():
    nurses = [Nurse(**r) for r in load("roster.json")]
    assert len(nurses) == 24
    assert sum("ACLS" in n.certifications for n in nurses) == 8


def test_mock_rules():
    rules = RulesConfig(**load("rules.json"))
    assert rules.min_rest_hours == 10
    assert rules.max_weekly_hours == 40
    assert rules.max_consecutive_shifts == 3


def test_mock_demand_follows_the_ratio():
    rules = RulesConfig(**load("rules.json"))
    rows = [DemandRow(**r) for r in load("demand.json")]
    assert len(rows) == 14  # 7 days x 2 shifts
    for r in rows:
        assert r.nurses_needed == math.ceil(r.patient_count / rules.ratio_patients_per_nurse)
        assert 4 <= r.nurses_needed <= 5


def test_mock_availability_covers_every_nurse_date_and_shift():
    rows = [AvailabilityRow(**r) for r in load("availability.json")]
    assert len(rows) == 24 * 7 * 2
    assert len({(r.nurse_id, r.date, r.shift) for r in rows}) == len(rows)
    roster_ids = {n["nurse_id"] for n in load("roster.json")}
    assert {r.nurse_id for r in rows} == roster_ids


def test_approved_time_off_shows_as_unavailable():
    rows = [AvailabilityRow(**r) for r in load("availability.json")]
    off = [r for r in rows if r.reason == "approved_time_off"]
    assert off and all(r.available is False for r in off)
    assert all(r.available is True for r in rows if r.reason == "none")


def test_reference_draft_fits_the_form_and_covers_demand():
    draft = Draft(**load("reference_draft.json"))
    demand = [DemandRow(**r) for r in load("demand.json")]
    for d in demand:
        got = [a for a in draft.assignments if a.date == d.date and a.shift == d.shift]
        assert len(got) == d.nurses_needed
    assert draft.open_gaps == [] and draft.unfixable == []


# --- the forms accept good data ----------------------------------------------------


def test_assignment_for_an_overnight_shift():
    a = Assignment(unit="7W", date="2026-11-02", shift="night", nurse_id="N001", shift_start="19:00", shift_end="07:00")
    assert a.shift_end == "07:00"


def test_draft_with_every_part():
    draft = Draft(
        case_id="case-1", snapshot_id="phase1-snapshot", version=2,
        assignments=[Assignment(unit="7W", date="2026-11-02", shift="day", nurse_id="N001", shift_start="07:00", shift_end="19:00")],
        open_gaps=[OpenGap(unit="7W", date="2026-11-03", shift="night", nurses_needed=4, nurses_assigned=3, gap_reason="no_certified_nurse")],
        notes=["Moved N002 to cover Tuesday night."],
        unfixable=[Unfixable(rule="certification", date="2026-11-03", shift="night", reason="No available nurse holds ACLS.")],
        suggestions=[Suggestion(date="2026-11-04", shift="day", nurse_id="N005", reason="Rested and available.")],
    )
    assert draft.version == 2


@pytest.mark.parametrize(
    "rule",
    ["rest_time", "weekly_hours", "consecutive_shifts", "certification", "availability", "coverage", "fairness"],
)
def test_violation_accepts_every_rule(rule):
    v = Violation(rule=rule, severity="hard", nurse_id="N003", date="2026-11-03", shift="day",
                  found="8 hours of rest", limit="10 hours of rest")
    assert v.fix_hint == ""  # added later by the Rules Checker agent


def test_coverage_violation_has_empty_nurse_id():
    v = Violation(rule="coverage", severity="hard", date="2026-11-05", shift="night", found="3 nurses", limit="4 nurses")
    assert v.nurse_id == ""


def test_callout_and_soft_tradeoff():
    Callout(nurse_id="N004", date="2026-11-03", shift="night", reported_at="2026-11-03T15:30:00")
    SoftTradeoff(rule="fairness", date="2026-11-08", shift="day", note="N007 has 3 more night shifts than N012.")


def test_check_rules_result_pass_and_fail():
    ok = CheckRulesResult(case_id="case-1", version=1, passed=True)
    assert ok.passed
    bad = CheckRulesResult(
        case_id="case-1", version=1, passed=False,
        violations=[Violation(rule="coverage", severity="hard", date="2026-11-05", shift="night", found="3 nurses", limit="4 nurses")],
    )
    assert not bad.passed


def test_soft_violation_does_not_fail_a_draft():
    r = CheckRulesResult(
        case_id="case-1", version=1, passed=True,
        violations=[Violation(rule="fairness", severity="soft", date="2026-11-08", shift="day", found="gap of 3", limit="gap of 2")],
    )
    assert r.passed


def test_missing_status_rows_have_empty_fields():
    d = DemandRow(unit="7W", date="2026-11-03", shift="day", status="missing", note="No patient count entered.")
    assert d.patient_count is None and d.nurses_needed is None
    a = AvailabilityRow(nurse_id="N001", date="2026-11-03", shift="day", status="missing", note="No data for this nurse.")
    assert a.available is None and a.reason is None


# --- the forms reject bad data -----------------------------------------------------


def test_rejects_unknown_shift_kind():
    with pytest.raises(ValidationError):
        Assignment(unit="7W", date="2026-11-02", shift="evening", nurse_id="N001", shift_start="15:00", shift_end="23:00")


def test_rejects_old_shape_fields():
    # The first draft used per-day availability and "id". The PRD does not.
    with pytest.raises(ValidationError):
        AvailabilityRow(nurse_id="N001", date="2026-11-02", availability="available", status="ok")
    with pytest.raises(ValidationError):
        Nurse(id="N001", name="Ada Brown", unit="7W", certifications=["ACLS"], hours_this_week=0)


def test_rejects_unknown_rule_and_severity():
    base = dict(date="2026-11-02", shift="day", found="x", limit="y")
    with pytest.raises(ValidationError):
        Violation(rule="snack_break", severity="hard", **base)
    with pytest.raises(ValidationError):
        Violation(rule="coverage", severity="medium", **base)


def test_rejects_invented_fields():
    with pytest.raises(ValidationError):
        Callout(nurse_id="N004", date="2026-11-03", shift="night", reported_at="x", mood="sick")


def test_rejects_draft_version_outside_1_to_3():
    with pytest.raises(ValidationError):
        Draft(case_id="case-1", snapshot_id="s", version=4, assignments=[])


def test_status_not_ok_needs_a_note():
    with pytest.raises(ValidationError):
        DemandRow(unit="7W", date="2026-11-02", shift="day", patient_count=20, nurses_needed=4, status="needs_review")
    with pytest.raises(ValidationError):
        AvailabilityRow(nurse_id="N001", date="2026-11-02", shift="day", available=True, reason="none", status="needs_review")


def test_missing_rows_must_be_empty():
    with pytest.raises(ValidationError):
        DemandRow(unit="7W", date="2026-11-02", shift="day", patient_count=20, status="missing", note="n")
    with pytest.raises(ValidationError):
        AvailabilityRow(nurse_id="N001", date="2026-11-02", shift="day", available=True, status="missing", note="n")


def test_present_availability_needs_available_and_reason():
    with pytest.raises(ValidationError):
        AvailabilityRow(nurse_id="N001", date="2026-11-02", shift="day", status="ok")


def test_a_draft_with_hard_violations_cannot_pass():
    with pytest.raises(ValidationError):
        CheckRulesResult(
            case_id="case-1", version=1, passed=True,
            violations=[Violation(rule="coverage", severity="hard", date="2026-11-05", shift="night", found="3", limit="4")],
        )
    with pytest.raises(ValidationError):
        CheckRulesResult(case_id="case-1", version=1, passed=False)


def test_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        Assignment(unit="7W", date="2026-11-02", shift="day", nurse_id="N001")
