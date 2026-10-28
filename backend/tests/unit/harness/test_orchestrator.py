"""The orchestrator writes row statuses itself and returns one case record."""

import json
from pathlib import Path

import pytest

from app.contract.case_record import CaseRecord
from app.contract.models import Draft
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import (
    HintingRulesChecker,
    ScriptedAvailabilityAgent,
    ScriptedDemandAgent,
    ScriptedScheduler,
)
from app.orchestrator import run_case, snapshot_id_for, stamp_demand

WEEK = "2026-11-02"


def _raw(name):
    """A mock file as an agent would return it: no status, no note."""
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def _run(demand=None, availability=None, case_id="case-1", leave=None):
    inputs = load_inputs()
    reference = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
    return run_case(
        ScriptedDemandAgent(_raw("demand.json") if demand is None else demand),
        ScriptedAvailabilityAgent(_raw("availability.json") if availability is None else availability),
        ScriptedScheduler([reference], case_id=case_id, snapshot_id=snapshot_id_for(case_id)),
        HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK, case_id, leave=leave,
    )


def test_clean_run_is_ready_for_the_manager():
    rec = _run()
    assert isinstance(rec, CaseRecord)
    assert (rec.status, rec.outcome) == ("waiting_approval", "passed")
    assert rec.snapshot_id == "snap-case-1" and rec.final_draft.snapshot_id == "snap-case-1"
    assert rec.demand_result.counts.ok == 14 and rec.availability_result.counts.ok == 336
    assert rec.manager_decision is None and rec.parent_case_id is None


def test_demand_agent_failure_marks_every_shift_missing_and_never_guesses():
    rec = _run(demand=RuntimeError("boom"))
    assert rec.demand_result.counts.missing == 14
    assert all(r.nurses_needed is None and "boom" in r.note for r in rec.demand_result.rows)


def test_absent_row_is_missing_and_shift_is_left_open():
    rows = _raw("demand.json")[1:]
    rec = _run(demand=rows)
    assert rec.demand_result.counts.missing == 1 and rec.demand_result.rows[0].status == "missing"


def test_agent_flag_and_ratio_mismatch_become_needs_review_with_value_kept():
    rows = _raw("demand.json")
    rows[0]["flag"] = "census may rise"
    rows[1]["nurses_needed"] = 9
    result = stamp_demand(rows, _snapshot())
    assert [r.status for r in result.rows[:2]] == ["needs_review", "needs_review"]
    assert result.rows[0].nurses_needed == 5 and "census" in result.rows[0].note
    assert "ratio" in result.rows[1].note and result.rows[1].nurses_needed == 9


def test_a_duplicate_row_is_missing_and_a_malformed_row_rejects_the_whole_result():
    rows = _raw("demand.json")
    rows.append(dict(rows[0]))
    result = stamp_demand(rows, _snapshot())
    assert result.rows[0].status == "missing" and "more than one" in result.rows[0].note
    assert result.rows[1].status == "ok"
    rows = _raw("demand.json")
    rows[2]["nurses_needed"] = -3
    result = stamp_demand(rows, _snapshot())
    assert result.counts.missing == 14 and "row 3, field nurses_needed" in result.rows[0].note


def test_availability_reason_conflict_is_needs_review():
    rows = _raw("availability.json")
    rows[0].update(available=True, reason="approved_time_off")
    rec = _run(availability=rows)
    assert rec.availability_result.rows[0].status == "needs_review"
    assert rec.availability_result.counts.needs_review == 1


def test_agents_cannot_change_the_snapshot():
    class Tamper(ScriptedDemandAgent):
        def run(self, snapshot):
            snapshot.roster.clear()
            return super().run(snapshot)

    inputs = load_inputs()
    reference = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
    rec = run_case(Tamper(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                   ScriptedScheduler([reference], snapshot_id=snapshot_id_for("case-1")), HintingRulesChecker(),
                   inputs.roster, inputs.rules, "7W", WEEK, "case-1")
    assert rec.availability_result.counts.ok == 336


def test_no_valid_draft_means_nothing_to_approve():
    inputs = load_inputs()
    rec = run_case(ScriptedDemandAgent(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                   ScriptedScheduler([None]), HintingRulesChecker(), inputs.roster, inputs.rules,
                   "7W", WEEK, "case-1")
    assert (rec.status, rec.outcome, rec.final_draft, rec.drafts) == ("waiting_approval", "stopped_after_3_rounds", None, [])


def _snapshot():
    from app.orchestrator import make_snapshot
    inputs = load_inputs()
    return make_snapshot(inputs.roster, inputs.rules, "7W", WEEK, "snap-x")


def test_snapshot_id_can_be_chosen_by_the_caller():
    inputs = load_inputs()
    reference = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
    rec = run_case(ScriptedDemandAgent(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                   ScriptedScheduler([reference], snapshot_id="snap-custom"), HintingRulesChecker(),
                   inputs.roster, inputs.rules, "7W", WEEK, "case-1", snapshot_id="snap-custom")
    assert rec.snapshot_id == "snap-custom" and rec.outcome == "passed"


def test_a_scheduler_with_the_wrong_snapshot_id_fails_every_round():
    inputs = load_inputs()
    reference = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
    rec = run_case(ScriptedDemandAgent(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                   ScriptedScheduler([reference], snapshot_id="phase1-snapshot"), HintingRulesChecker(),
                   inputs.roster, inputs.rules, "7W", WEEK, "case-1")
    assert rec.final_draft is None and rec.outcome == "stopped_after_3_rounds" and all("labeled" in r.error for r in rec.rounds)


def _leave_rows():
    return json.loads((Path(DEFAULT_DATA) / "leave.json").read_text())


def test_available_on_an_approved_leave_day_is_set_to_unavailable_and_flagged():
    rows = _raw("availability.json")  # mock leave: N003 approved PTO on 2026-11-04; the agent says available
    for r in rows:
        if r["nurse_id"] == "N003" and r["date"] == "2026-11-04":
            r.update(available=True, reason="none")
    rec = _run(availability=rows, leave=_leave_rows())
    flagged = [r for r in rec.availability_result.rows if r.status == "needs_review"]
    assert flagged and all("approved" in r.note and "leave" in r.note and "set to unavailable" in r.note for r in flagged)
    n003 = [r for r in flagged if r.nurse_id == "N003"]
    assert {(r.date, r.shift) for r in n003} == {("2026-11-04", "day"), ("2026-11-04", "night")}
    assert all((r.available, r.reason) == (False, "approved_time_off") for r in n003)  # code overrides the agent


def test_a_nurse_on_approved_leave_can_no_longer_be_booked_even_if_the_agent_said_available():
    leave = [{"employeeId": "N006", "start": "2026-11-04", "end": "2026-11-04", "type": "pto", "status": "approved"}]
    rec = _run(leave=leave)  # the reference draft has N006 on 2026-11-04 day; the mock agent says N006 is available
    first = [v for vv in rec.violations if vv.version == 1 for v in vv.violations]
    assert ("availability", "N006", "2026-11-04", "day") in [(v.rule, v.nurse_id, v.date, v.shift) for v in first]
    assert "approved time off" in [v.found for v in first if v.rule == "availability"][0]
    assert rec.outcome == "stopped_after_3_rounds"  # the scripted Scheduler keeps booking N006, so it is not "passing"


def test_pending_denied_and_broken_leave_is_ignored():
    leave = [
        {"employeeId": "N003", "start": "2026-11-04", "end": "2026-11-04", "type": "pto", "status": "pending"},
        {"employeeId": "N003", "start": "2026-11-04", "end": "2026-11-04", "type": "pto", "status": "denied"},
        {"employeeId": "N003", "start": "soon", "end": "later", "status": "approved"},
        "junk", None, {"status": "approved"},
    ]
    assert _run(leave=leave).availability_result.counts.needs_review == 0


def test_mock_week_with_its_real_leave_file_is_clean():
    assert _run(leave=_leave_rows()).availability_result.counts.needs_review == 0


def test_agent_already_saying_unavailable_on_leave_day_stays_ok():
    rows = _raw("availability.json")
    for r in rows:
        if r["nurse_id"] == "N003" and r["date"] == "2026-11-04":
            r.update(available=False, reason="approved_time_off")
    rec = _run(availability=rows, leave=_leave_rows())
    assert not [r for r in rec.availability_result.rows if r.nurse_id == "N003" and r.date == "2026-11-04"
                and r.status != "ok"]


def test_multi_day_leave_covers_every_day():
    leave = [{"employeeId": "N001", "start": "2026-11-02", "end": "2026-11-03", "type": "vacation",
              "status": "approved"}]
    flagged = [r for r in _run(leave=leave).availability_result.rows if r.status == "needs_review"]
    assert {(r.nurse_id, r.date) for r in flagged} == {("N001", "2026-11-02"), ("N001", "2026-11-03")}


# --- PRD case record fields and stop-on-missing ---------------------------------------


def _run_with(scheduler, demand=None, availability=None):
    inputs = load_inputs()
    return run_case(
        ScriptedDemandAgent(_raw("demand.json") if demand is None else demand),
        ScriptedAvailabilityAgent(_raw("availability.json") if availability is None else availability),
        scheduler, HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK, "case-1",
    )


def _reference_scheduler():
    reference = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
    return ScriptedScheduler([reference], snapshot_id=snapshot_id_for("case-1"))


def test_record_uses_the_prd_fields():
    rec = _run()
    assert (rec.trigger, rec.status, rec.rounds_used) == ("weekly", "waiting_approval", 1)
    assert len(rec.affected_shifts) == 14 and (rec.affected_shifts[0].date, rec.affected_shifts[0].shift) == (WEEK, "day")
    assert rec.start_time and [d.version for d in rec.drafts] == [1] and rec.final_draft == rec.drafts[0]
    assert [(v.version, v.violations) for v in rec.violations] == [(1, [])]
    assert rec.manager_decision is None and rec.decision_time is None and rec.stop_reason == ""


def test_every_checked_draft_and_its_violations_are_kept():
    reference = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
    short = reference.model_copy(update={"assignments": reference.assignments[3:]})
    inputs = load_inputs()
    rec = run_case(ScriptedDemandAgent(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                   ScriptedScheduler([short, short, reference], snapshot_id=snapshot_id_for("case-1")),
                   HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK, "case-1")
    assert (rec.outcome, rec.rounds_used) == ("passed", 3)
    assert [d.version for d in rec.drafts] == [1, 2, 3]
    by_version = {v.version: v.violations for v in rec.violations}
    assert by_version[1] and by_version[2] and by_version[3] == []
    assert all(v.severity == "hard" for v in by_version[1])


def test_a_missing_demand_row_stops_before_the_scheduler_runs():
    scheduler = _reference_scheduler()
    rec = _run_with(scheduler, demand=_raw("demand.json")[1:])
    assert scheduler.calls == []  # the Scheduler never ran
    assert (rec.status, rec.outcome, rec.rounds_used) == ("waiting_approval", "stopped_missing_input", 0)
    assert rec.drafts == [] and rec.final_draft is None and rec.violations == []
    assert rec.stop_reason.startswith("Stopped before scheduling") and "1 demand row(s)" in rec.stop_reason
    assert [(n.item_type, n.id) for n in rec.needs_manual_review] == [("demand_day", f"{WEEK} day")]
    assert "\n" not in rec.stop_reason


def test_an_availability_agent_failure_stops_the_run_and_lists_every_nurse():
    scheduler = _reference_scheduler()
    rec = _run_with(scheduler, availability=RuntimeError("timed out"))
    assert scheduler.calls == [] and rec.outcome == "stopped_missing_input"
    assert "336 availability row(s)" in rec.stop_reason and "timed out" in rec.stop_reason
    assert len([n for n in rec.needs_manual_review if n.item_type == "nurse"]) == 24


def test_a_row_with_a_shift_outside_the_allowed_list_stops_the_run():
    rows = _raw("demand.json")
    rows[0]["shift"] = "evening"  # outside the allowed list
    scheduler = _reference_scheduler()
    rec = _run_with(scheduler, demand=rows)
    assert scheduler.calls == [] and rec.outcome == "stopped_missing_input"
    assert rec.demand_result.rows[0].status == "missing"


def test_needs_review_alone_does_not_stop_the_run():
    rows = _raw("demand.json")
    rows[0]["flag"] = "census may rise"
    rec = _run_with(_reference_scheduler(), demand=rows)
    assert rec.outcome == "passed" and rec.demand_result.counts.needs_review == 1


def test_a_stopped_case_cannot_be_approved_but_can_be_rejected():
    from app.decisions import DecisionRefused, approve, reject
    rec = _run_with(_reference_scheduler(), demand=_raw("demand.json")[1:])
    with pytest.raises(DecisionRefused, match="required input is missing"):
        approve(rec)
    assert reject(rec).outcome == "rejected"
