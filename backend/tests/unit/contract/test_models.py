"""Tests that the handoff formats accept good data and reject bad data. Owner: Shared."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contract.models import (
    Assignment,
    AvailabilityRow,
    Callout,
    DemandRow,
    LeaveRequest,
    Nurse,
    Snapshot,
    Unfixable,
    Violation,
)

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"


def load(name):
    return json.loads((MOCK / name).read_text())


# --- the mock data fits the forms -------------------------------------------------


def test_mock_nurses_fit_the_form():
    nurses = [
        Nurse(**{k: v for k, v in r.items() if k != "isAdmin"})
        for r in load("roster.json")
        if not r["isAdmin"]
    ]
    assert len(nurses) == 16


def test_mock_demand_fits_the_form():
    rows = [DemandRow(**r) for r in load("demand.json")]
    assert len(rows) == 56
    missing = [r for r in rows if r.nurses_needed is None]
    assert len(missing) == 1 and missing[0].date == "2026-11-17"


def test_whole_mock_snapshot_fits_the_forms():
    nurses = [
        Nurse(**{k: v for k, v in r.items() if k != "isAdmin"})
        for r in load("roster.json")
        if not r["isAdmin"]
    ]
    availability = [
        AvailabilityRow(
            nurse_id=nid,
            date=date,
            availability=entry["status"],
            reason=entry["reason"],
            note=entry["note"],
        )
        for nid, days in load("availability.json").items()
        for date, entry in days.items()
    ]
    leave = [
        LeaveRequest(
            id=r["id"], nurse_id=r["employeeId"], type=r["type"],
            start=r["start"], end=r["end"], note=r["note"], status=r["status"],
        )
        for r in load("leave.json")
    ]
    callouts = [
        Callout(
            id=r["id"], nurse_id=r["employeeId"], shift_id=r["shiftId"], date=r["date"],
            shift=r["shift"], reason=r["reason"], reported_at=r["reportedAt"],
        )
        for r in load("callouts.json")
    ]
    snapshot = Snapshot(
        snapshot_id="mock-001",
        unit="Med-Surg",
        start_date="2026-11-02",
        end_date="2026-11-29",
        nurses=nurses,
        demand=[DemandRow(**r) for r in load("demand.json")],
        availability=availability,
        leave=leave,
        callouts=callouts,
    )
    assert len(snapshot.nurses) == 16
    assert len(snapshot.leave) == 5


# --- the forms accept good data ---------------------------------------------------


def test_assignment():
    a = Assignment(nurse_id="n01", date="2026-11-02", shift="day")
    assert a.shift == "day"


@pytest.mark.parametrize(
    "rule",
    ["rest_time", "weekly_hours", "consecutive_shifts", "certification", "availability", "coverage"],
)
def test_violation_accepts_every_rule(rule):
    v = Violation(
        rule=rule, severity="hard", nurse_id="n06", date="2026-11-07", shift="day",
        found=0, limit=10, fix_hint="Move one shift",
    )
    assert v.rule == rule


def test_coverage_violation_has_empty_nurse_id():
    v = Violation(
        rule="coverage", severity="hard", date="2026-11-05", shift="night",
        found=2, limit=3, fix_hint="Add one nurse",
    )
    assert v.nurse_id == ""


def test_unfixable_row():
    u = Unfixable(
        rule="coverage", date="2026-11-05", shift="night",
        reason="No other nurse is available on that night.",
    )
    assert u.nurse_id == ""


def test_demand_row_status_is_optional_and_checked():
    base = dict(date="2026-11-02", shift="day", start="07:00", end="19:00", unit="Med-Surg")
    assert DemandRow(**base).status is None
    assert DemandRow(**base, nurses_needed=3, status="ok").status == "ok"


# --- the forms reject bad data ----------------------------------------------------


def test_rejects_unknown_shift_kind():
    with pytest.raises(ValidationError):
        Assignment(nurse_id="n01", date="2026-11-02", shift="evening")


def test_rejects_unknown_rule():
    with pytest.raises(ValidationError):
        Violation(
            rule="snack_break", severity="hard", date="2026-11-02", shift="day",
            found=1, limit=2, fix_hint="x",
        )


def test_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        Violation(
            rule="coverage", severity="medium", date="2026-11-02", shift="day",
            found=1, limit=2, fix_hint="x",
        )


def test_rejects_invented_fields():
    with pytest.raises(ValidationError):
        Assignment(nurse_id="n01", date="2026-11-02", shift="day", mood="happy")


def test_rejects_bad_row_status():
    with pytest.raises(ValidationError):
        AvailabilityRow(nurse_id="n01", date="2026-11-02", availability="available", status="maybe")


def test_rejects_bad_availability_answer():
    with pytest.raises(ValidationError):
        AvailabilityRow(nurse_id="n01", date="2026-11-02", availability="ok")


def test_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        Assignment(nurse_id="n01", shift="day")
