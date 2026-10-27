"""Unit tests for check_rules, using small hand-made schedules with known violations.

Owner: Cheich. A bug in check_rules would pass bad schedules, so every rule is tested on its own,
at its boundary, and together with the others.

Week used in the tests: Monday 2026-11-02 to Sunday 2026-11-08. Shifts are 12 hours:
day 07:00-19:00, night 19:00-07:00 (ends the next morning).
"""

import json
from pathlib import Path

import pytest

from app.contract.models import (
    Assignment,
    AvailabilityRow,
    DemandRow,
    Draft,
    Nurse,
    RulesConfig,
    Unfixable,
)
from app.harness.rules import DraftRejected, check_rules, check_rules_from_dicts

MON, TUE, WED, THU, FRI, SAT, SUN = (f"2026-11-0{i}" for i in range(2, 9))
WEEK = [MON, TUE, WED, THU, FRI, SAT, SUN]
TIMES = {"day": ("07:00", "19:00"), "night": ("19:00", "07:00")}

RULES = RulesConfig(
    min_rest_hours=10, max_weekly_hours=40, max_consecutive_shifts=3,
    required_certifications_per_shift=["ACLS"], ratio_patients_per_nurse=5, max_fairness_gap=2,
)


# --- helpers -----------------------------------------------------------------------


def nurse(i, acls=False, hours=0):
    return Nurse(nurse_id=f"N{i:03d}", name=f"Nurse {i}", unit="7W",
                 certifications=["BLS", "ACLS"] if acls else ["BLS"], hours_this_week=hours)


def asg(i, date, shift, start=None, end=None):
    s, e = TIMES[shift]
    return Assignment(unit="7W", date=date, shift=shift, nurse_id=f"N{i:03d}",
                      shift_start=start or s, shift_end=end or e)


def demand(date, shift, n):
    return DemandRow(unit="7W", date=date, shift=shift, patient_count=n * 5, nurses_needed=n, status="ok")


def available(nurses, extra_off=None, dates=None):
    """Every nurse available on every date and shift, except the (nurse, date, shift) in extra_off."""
    off = extra_off or {}
    rows = []
    for n in nurses:
        for d in dates or WEEK:
            for s in ("day", "night"):
                reason = off.get((n.nurse_id, d, s))
                rows.append(AvailabilityRow(nurse_id=n.nurse_id, date=d, shift=s, available=reason is None,
                                            reason=reason or "none", status="ok",
                                            note="Approved time off" if reason else ""))
    return rows


def draft(assignments, version=1, **extra):
    return Draft(case_id="case-1", snapshot_id="phase1-snapshot", version=version, assignments=assignments, **extra)


def run(assignments, demand_rows, nurses, availability=None, rules=RULES, **kw):
    return check_rules(draft(assignments, **kw), demand_rows, availability if availability is not None else available(nurses), nurses, rules)


def rules_found(result):
    return sorted(v.rule for v in result.violations)


@pytest.fixture
def staff():
    # N001 holds ACLS, N002 to N006 do not
    return [nurse(1, acls=True)] + [nurse(i) for i in range(2, 7)]


# --- a correct schedule passes -----------------------------------------------------


def test_correct_schedule_passes(staff):
    result = run([asg(1, MON, "day"), asg(2, MON, "day")], [demand(MON, "day", 2)], staff)
    assert result.passed and result.violations == []


def test_result_echoes_case_id_and_version(staff):
    result = run([asg(1, MON, "day")], [demand(MON, "day", 1)], staff, version=3)
    assert (result.case_id, result.version) == ("case-1", 3)


# --- rest time ---------------------------------------------------------------------


def test_overnight_turnaround_fails_rest_time(staff):
    """PRD eval case 4: Monday night 19:00-07:00, then Tuesday day 07:00-19:00 gives 0 hours of rest."""
    drafted = [asg(1, MON, "night"), asg(1, TUE, "day")]
    result = run(drafted, [demand(MON, "night", 1), demand(TUE, "day", 1)], staff)
    assert not result.passed
    (v,) = result.violations
    assert (v.rule, v.severity, v.nurse_id, v.date, v.shift) == ("rest_time", "hard", "N001", TUE, "day")
    assert (v.found, v.limit) == ("0 hours of rest", "10 hours of rest")


def _rules_with(**changes):
    return RULES.model_copy(update=changes)


def test_rest_of_exactly_the_minimum_passes(staff):
    # day ends 19:00 Monday and the next day shift starts 07:00 Tuesday: exactly 12 hours of rest
    drafted = [asg(1, MON, "day"), asg(1, TUE, "day")]
    assert run(drafted, [], staff, rules=_rules_with(min_rest_hours=12)).passed


def test_rest_just_under_the_minimum_fails(staff):
    # the same 12 hours of rest, but the minimum is 13
    drafted = [asg(1, MON, "day"), asg(1, TUE, "day")]
    result = run(drafted, [], staff, rules=_rules_with(min_rest_hours=13))
    assert rules_found(result) == ["rest_time"]
    assert (result.violations[0].found, result.violations[0].limit) == ("12 hours of rest", "13 hours of rest")


def test_two_night_shifts_in_a_row_have_enough_rest(staff):
    assert run([asg(1, MON, "night"), asg(1, TUE, "night")], [], staff).passed


def test_day_then_night_on_the_same_date_fails_rest_time(staff):
    result = run([asg(1, MON, "day"), asg(1, MON, "night")], [], staff)
    assert rules_found(result) == ["rest_time"]


def test_overlapping_shifts_are_reported(staff):
    # the same shift listed twice overlaps itself
    result = run([asg(1, MON, "day"), asg(1, MON, "day")], [], staff)
    assert result.violations[0].found == "overlapping shifts"


# --- weekly hours ------------------------------------------------------------------


def test_three_twelve_hour_shifts_pass(staff):
    assert run([asg(1, MON, "day"), asg(1, WED, "day"), asg(1, FRI, "day")], [], staff).passed


def test_four_shifts_exceed_forty_hours(staff):
    drafted = [asg(1, d, "day") for d in (MON, WED, FRI, SUN)]
    result = run(drafted, [], staff)
    (v,) = result.violations
    assert (v.rule, v.nurse_id, v.date, v.shift) == ("weekly_hours", "N001", SUN, "day")  # the shift that crosses 40
    assert (v.found, v.limit) == ("48 hours this week", "40 hours max")


def test_hours_already_worked_this_week_count():
    nurses = [nurse(1, acls=True, hours=8)]
    drafted = [asg(1, d, "day") for d in (MON, WED, FRI)]  # 8 + 36 = 44
    result = run(drafted, [], nurses)
    assert result.violations[0].found == "44 hours this week"


def test_exactly_forty_hours_passes():
    nurses = [nurse(1, acls=True, hours=4)]
    assert run([asg(1, d, "day") for d in (MON, WED, FRI)], [], nurses).passed  # 4 + 36 = 40


def test_weekly_hours_are_counted_per_week(staff):
    next_mon, next_wed, next_fri = "2026-11-09", "2026-11-11", "2026-11-13"
    drafted = [asg(1, d, "day") for d in (MON, WED, FRI, next_mon, next_wed, next_fri)]
    two_weeks = WEEK + ["2026-11-09", "2026-11-11", "2026-11-13"]
    assert run(drafted, [], staff, availability=available(staff, dates=two_weeks)).passed  # 36 hours in each week


# --- consecutive shifts ------------------------------------------------------------


def test_three_days_in_a_row_pass(staff):
    assert run([asg(1, d, "day") for d in (MON, TUE, WED)], [], staff).passed


def test_four_days_in_a_row_fail(staff):
    result = run([asg(1, d, "day") for d in (MON, TUE, WED, THU)], [], staff)
    assert "consecutive_shifts" in rules_found(result)
    v = [x for x in result.violations if x.rule == "consecutive_shifts"][0]
    assert (v.nurse_id, v.date, v.shift) == ("N001", THU, "day")
    assert (v.found, v.limit) == ("4 shifts in a row", "3 shifts max")


def test_a_day_off_resets_the_run(staff):
    drafted = [asg(1, d, "day") for d in (MON, TUE, WED, FRI, SAT)]  # 3 then a break then 2
    assert "consecutive_shifts" not in rules_found(run(drafted, [], staff))


def test_one_violation_per_run(staff):
    drafted = [asg(1, d, "day") for d in (MON, TUE, WED, THU, FRI)]  # a run of 5
    result = run(drafted, [], staff)
    consecutive = [v for v in result.violations if v.rule == "consecutive_shifts"]
    assert len(consecutive) == 1 and consecutive[0].found == "5 shifts in a row"


# --- certification -----------------------------------------------------------------


def test_shift_without_the_required_certification_fails(staff):
    result = run([asg(2, MON, "day"), asg(3, MON, "day")], [demand(MON, "day", 2)], staff)
    (v,) = result.violations
    assert (v.rule, v.nurse_id, v.date, v.shift) == ("certification", "", MON, "day")
    assert (v.found, v.limit) == ("0 nurses with ACLS", "1 nurse with ACLS")


def test_one_certified_nurse_is_enough(staff):
    assert run([asg(1, MON, "day"), asg(2, MON, "day")], [demand(MON, "day", 2)], staff).passed


def test_empty_shift_fails_certification_and_coverage(staff):
    result = run([], [demand(MON, "night", 2)], staff)
    assert rules_found(result) == ["certification", "coverage"]


# --- availability ------------------------------------------------------------------


def test_scheduled_on_approved_time_off_fails(staff):
    off = {("N001", MON, "day"): "approved_time_off"}
    result = run([asg(1, MON, "day")], [], staff, availability=available(staff, off))
    (v,) = result.violations
    assert (v.rule, v.nurse_id, v.date, v.shift) == ("availability", "N001", MON, "day")
    assert (v.found, v.limit) == ("unavailable (approved time off)", "available")


def test_scheduled_after_a_call_out_fails(staff):
    off = {("N001", TUE, "night"): "call_out"}
    result = run([asg(1, TUE, "night")], [], staff, availability=available(staff, off))
    assert result.violations[0].found == "unavailable (a call-out)"


def test_unavailable_for_one_shift_only_does_not_block_the_other(staff):
    off = {("N001", MON, "night"): "approved_time_off"}
    assert run([asg(1, MON, "day")], [], staff, availability=available(staff, off)).passed


def test_no_availability_row_counts_as_unavailable(staff):
    result = run([asg(1, MON, "day")], [], staff, availability=[])
    assert result.violations[0].found == "no availability data"


def test_missing_status_row_counts_as_unavailable(staff):
    rows = [AvailabilityRow(nurse_id="N001", date=MON, shift="day", status="missing", note="No data for this nurse.")]
    result = run([asg(1, MON, "day")], [], staff, availability=rows)
    assert result.violations[0].found == "no availability data"


def test_needs_review_row_uses_the_value_it_has(staff):
    rows = [AvailabilityRow(nurse_id="N001", date=MON, shift="day", available=True, reason="none",
                            status="needs_review", note="Looks odd")]
    assert run([asg(1, MON, "day")], [], staff, availability=rows).passed


# --- coverage ----------------------------------------------------------------------


def test_too_few_nurses_fails_coverage(staff):
    result = run([asg(1, MON, "day"), asg(2, MON, "day")], [demand(MON, "day", 4)], staff)
    (v,) = result.violations
    assert (v.rule, v.nurse_id, v.date, v.shift) == ("coverage", "", MON, "day")
    assert (v.found, v.limit) == ("2 nurses", "4 nurses")


def test_single_nurse_uses_the_singular(staff):
    result = run([asg(1, MON, "day")], [demand(MON, "day", 2)], staff)
    assert (result.violations[0].found, result.violations[0].limit) == ("1 nurse", "2 nurses")


def test_more_nurses_than_needed_is_not_a_violation(staff):
    assert run([asg(1, MON, "day"), asg(2, MON, "day"), asg(3, MON, "day")], [demand(MON, "day", 2)], staff).passed


def test_demand_with_missing_status_is_not_checked_for_coverage(staff):
    row = DemandRow(unit="7W", date=MON, shift="day", status="missing", note="No patient count entered.")
    assert run([], [row], staff).passed


# --- fairness is soft --------------------------------------------------------------


def _fairness_world():
    nurses = [nurse(1, acls=True), nurse(2, acls=True), nurse(3, acls=True)]
    return nurses


def test_fairness_gap_above_the_limit_is_soft_and_never_fails():
    nurses = _fairness_world()
    # N001 works 3 nights (3 night/weekend shifts); N002 and N003 work none: gap 3 > 2
    drafted = [asg(1, MON, "night"), asg(1, WED, "night"), asg(1, FRI, "night"),
               asg(2, MON, "day"), asg(3, TUE, "day")]
    result = run(drafted, [], nurses)
    assert result.passed and result.violations == []
    (soft,) = result.soft_tradeoffs
    assert (soft.rule, soft.nurse_id, soft.date, soft.shift) == ("fairness", "N001", MON, "night")
    assert "gap is 3" in soft.note


def test_fairness_gap_at_the_limit_is_fine():
    nurses = _fairness_world()
    drafted = [asg(1, MON, "night"), asg(1, WED, "night"), asg(2, TUE, "day"), asg(3, THU, "day")]  # gap 2
    assert run(drafted, [], nurses).soft_tradeoffs == []


def test_saturday_and_sunday_count_as_weekend_shifts():
    nurses = _fairness_world()
    drafted = [asg(1, SAT, "day"), asg(1, SUN, "day"), asg(1, FRI, "night"), asg(2, MON, "day"), asg(3, TUE, "day")]
    result = run(drafted, [], nurses)
    assert result.soft_tradeoffs and result.soft_tradeoffs[0].nurse_id == "N001"


# --- several problems at once, and ordering ----------------------------------------


def test_every_problem_is_reported_and_sorted_coverage_and_availability_first(staff):
    off = {("N002", TUE, "day"): "approved_time_off"}
    drafted = [asg(1, MON, "night"), asg(1, TUE, "day"),  # rest_time for N001
               asg(2, TUE, "day")]                         # availability for N002
    result = run(drafted, [demand(TUE, "day", 3)], staff, availability=available(staff, off))
    assert rules_found(result) == ["availability", "coverage", "rest_time"]
    assert [v.rule for v in result.violations][:2] == ["coverage", "availability"]


# --- the checker ignores the Scheduler's explanations ------------------------------


def test_notes_and_unfixable_rows_do_not_change_the_answer(staff):
    base = [asg(1, MON, "night"), asg(1, TUE, "day")]
    plain = run(base, [], staff)
    explained = run(
        base, [], staff,
        notes=["This is fine, N001 asked for it."],
        unfixable=[Unfixable(rule="rest_time", nurse_id="N001", date=TUE, shift="day", reason="Nobody else can cover.")],
    )
    assert plain.passed == explained.passed is False
    assert plain.violations == explained.violations


# --- a draft that cannot be parsed -------------------------------------------------


def test_unparseable_draft_is_rejected(staff):
    with pytest.raises(DraftRejected):
        check_rules_from_dicts({"case_id": "case-1"}, [], [], staff, RULES)


def test_draft_with_an_unknown_shift_is_rejected(staff):
    raw = {"case_id": "case-1", "snapshot_id": "s", "version": 1,
           "assignments": [{"unit": "7W", "date": MON, "shift": "evening", "nurse_id": "N001",
                            "shift_start": "15:00", "shift_end": "23:00"}]}
    with pytest.raises(DraftRejected):
        check_rules_from_dicts(raw, [], [], staff, RULES)


def test_a_good_raw_draft_is_checked(staff):
    raw = {"case_id": "case-9", "snapshot_id": "s", "version": 2, "assignments": []}
    result = check_rules_from_dicts(raw, [], [], staff, RULES)
    assert result.passed and (result.case_id, result.version) == ("case-9", 2)


# --- the real mock data ------------------------------------------------------------

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"


def _load(name):
    return json.loads((MOCK / name).read_text())


def _mock_world():
    return (
        Draft(**_load("reference_draft.json")),
        [DemandRow(**r) for r in _load("demand.json")],
        [AvailabilityRow(**r) for r in _load("availability.json")],
        [Nurse(**r) for r in _load("roster.json")],
        RulesConfig(**_load("rules.json")),
    )


def test_reference_draft_passes_every_hard_rule():
    d, dem, av, ro, ru = _mock_world()
    result = check_rules(d, dem, av, ro, ru)
    assert result.passed and result.violations == []
    assert result.soft_tradeoffs == []  # fairness gap is 2, at the limit


def test_removing_one_assignment_breaks_coverage():
    d, dem, av, ro, ru = _mock_world()
    d.assignments.pop(0)
    result = check_rules(d, dem, av, ro, ru)
    assert "coverage" in rules_found(result) and not result.passed


def test_moving_a_nurse_onto_approved_time_off_breaks_availability():
    d, dem, av, ro, ru = _mock_world()
    off = next(r for r in av if r.reason == "approved_time_off")
    target = next(a for a in d.assignments if a.date == off.date and a.shift == off.shift)
    target.nurse_id = off.nurse_id
    result = check_rules(d, dem, av, ro, ru)
    assert any(v.rule == "availability" and v.nurse_id == off.nurse_id for v in result.violations)


def test_giving_a_nurse_a_fourth_shift_breaks_weekly_hours():
    d, dem, av, ro, ru = _mock_world()
    busy = next(n for n in {a.nurse_id for a in d.assignments}
                if sum(1 for a in d.assignments if a.nurse_id == n) == 3)
    free_slot = next(a for a in d.assignments if a.nurse_id != busy
                     and not any(b.nurse_id == busy and b.date == a.date for b in d.assignments))
    free_slot.nurse_id = busy
    result = check_rules(d, dem, av, ro, ru)
    assert any(v.rule == "weekly_hours" and v.nurse_id == busy and v.found == "48 hours this week"
               for v in result.violations)
