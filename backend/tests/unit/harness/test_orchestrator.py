"""The orchestrator writes row statuses itself and returns one case record."""

import json
from pathlib import Path

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
    assert (rec.state, rec.outcome) == ("awaiting_approval", "passed")
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


def test_duplicate_and_unreadable_rows_are_missing():
    rows = _raw("demand.json")
    rows.append(dict(rows[0]))
    rows[2]["nurses_needed"] = -3
    result = stamp_demand(rows, _snapshot())
    assert result.rows[0].status == "missing" and "more than one" in result.rows[0].note
    assert result.rows[2].status == "missing" and "could not be read" in result.rows[2].note


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


def test_no_valid_draft_means_failed_not_approved():
    inputs = load_inputs()
    rec = run_case(ScriptedDemandAgent(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                   ScriptedScheduler([None]), HintingRulesChecker(), inputs.roster, inputs.rules,
                   "7W", WEEK, "case-1")
    assert (rec.state, rec.outcome, rec.final_draft) == ("failed", None, None)


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
    assert rec.state == "failed" and all("labeled" in r.error for r in rec.rounds)


def _leave_rows():
    return json.loads((Path(DEFAULT_DATA) / "leave.json").read_text())


def test_available_on_an_approved_leave_day_is_needs_review():
    rows = _raw("availability.json")  # mock leave: N003 approved PTO on 2026-11-04; the agent says available
    for r in rows:
        if r["nurse_id"] == "N003" and r["date"] == "2026-11-04":
            r.update(available=True, reason="none")
    rec = _run(availability=rows, leave=_leave_rows())
    flagged = [r for r in rec.availability_result.rows if r.status == "needs_review"]
    assert flagged and all("approved" in r.note and "leave" in r.note for r in flagged)
    n003 = [r for r in flagged if r.nurse_id == "N003"]
    assert {(r.date, r.shift) for r in n003} == {("2026-11-04", "day"), ("2026-11-04", "night")}
    assert all(r.available is True for r in n003)  # the value is kept


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
