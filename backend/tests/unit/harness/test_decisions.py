"""The manager's decisions and the case store. No API calls: scripted agents only."""

import json
from pathlib import Path

import pytest

from app.case_store import CaseStore, CaseStoreError
from app.contract.case_record import DemandChange
from app.contract.models import Draft
from app.decisions import DecisionRefused, approve, change_demand, has_open_issues, mark_out_of_date, reject
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import (
    HintingRulesChecker,
    ScriptedAvailabilityAgent,
    ScriptedDemandAgent,
    ScriptedScheduler,
)
from app.orchestrator import run_case, snapshot_id_for

WEEK = "2026-11-02"
REFERENCE = json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text())


def _raw(name):
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def _case(drafts=None, case_id="case-1", demand=None):
    inputs = load_inputs()
    return run_case(
        ScriptedDemandAgent(_raw("demand.json") if demand is None else demand),
        ScriptedAvailabilityAgent(_raw("availability.json")),
        ScriptedScheduler(drafts or [REFERENCE], case_id=case_id, snapshot_id=snapshot_id_for(case_id)),
        HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK, case_id,
    )


def _with_open_issues():
    broken = Draft(**REFERENCE).model_copy(update={"assignments": Draft(**REFERENCE).assignments[3:]})
    return _case(drafts=[broken])  # three rounds of the same short-staffed draft


def test_approve_a_clean_draft():
    rec = approve(_case(), now=lambda: __import__("datetime").datetime(2026, 11, 1, 9, 0))
    assert rec.state == "approved" and rec.manager_decision.action == "approve"
    assert rec.manager_decision.decided_at == "2026-11-01T09:00:00" and not rec.manager_decision.acknowledged_open_issues


def test_approving_open_issues_needs_an_explicit_acknowledgement_that_is_saved():
    rec = _with_open_issues()
    assert rec.outcome == "stopped_after_3_rounds" and has_open_issues(rec)
    with pytest.raises(DecisionRefused, match="open issues"):
        approve(rec)
    done = approve(rec, acknowledge_open_issues=True)
    assert done.state == "approved" and done.manager_decision.acknowledged_open_issues is True


def test_reject():
    rec = reject(_case())
    assert (rec.state, rec.manager_decision.action) == ("rejected", "reject")


def test_the_original_record_is_never_changed_in_place():
    original = _case()
    approve(original)
    assert original.state == "awaiting_approval" and original.manager_decision is None


def test_decided_out_of_date_and_failed_cases_refuse_every_decision():
    decided = approve(_case())
    for action in (lambda r: approve(r), lambda r: reject(r), lambda r: mark_out_of_date(r, "case-2")):
        with pytest.raises(DecisionRefused, match="already approved"):
            action(decided)
    stale = mark_out_of_date(_case(), "case-2")
    with pytest.raises(DecisionRefused, match="out of date.*case-2"):
        approve(stale)
    failed = _case(drafts=[None])
    assert failed.state == "failed"
    with pytest.raises(DecisionRefused, match="nothing to decide"):
        approve(failed)


def test_change_demand_starts_a_child_case_and_retires_the_old_one():
    old = _case()
    change = [DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=4)]
    scheduler_args = []

    def factory(case_id, snapshot_id):
        scheduler_args.append((case_id, snapshot_id))
        # the same week with one fewer nurse on Monday day, so it still passes
        draft = Draft(**REFERENCE)
        first = [a for a in draft.assignments if (a.date, a.shift) == ("2026-11-02", "day")][1]  # not the ACLS nurse
        trimmed = draft.model_copy(update={"assignments": [a for a in draft.assignments if a is not first]})
        return ScriptedScheduler([trimmed], case_id=case_id, snapshot_id=snapshot_id)

    inputs = load_inputs()
    retired, child = change_demand(old, change, "case-2", factory, HintingRulesChecker(), inputs.roster, inputs.rules)
    assert scheduler_args == [("case-2", "snap-case-2")]
    assert (retired.state, retired.newer_case_id) == ("out_of_date", "case-2")
    assert retired.manager_decision.action == "change_demand" and retired.manager_decision.new_case_id == "case-2"
    assert child.parent_case_id == "case-1" and child.snapshot_id == "snap-case-2"
    assert (child.state, child.outcome) == ("awaiting_approval", "passed")
    row = [r for r in child.demand_result.rows if (r.date, r.shift) == ("2026-11-02", "day")][0]
    assert (row.nurses_needed, row.status, row.note) == (4, "ok", "set by manager (was 5)")
    assert child.availability_result == old.availability_result
    with pytest.raises(DecisionRefused):
        approve(retired)


def test_manager_can_fill_in_a_missing_demand_row():
    old = _case(demand=_raw("demand.json")[1:])
    assert old.demand_result.rows[0].status == "missing"
    change = [DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=5)]
    inputs = load_inputs()
    _, child = change_demand(old, change, "case-2",
                             lambda c, s: ScriptedScheduler([REFERENCE], case_id=c, snapshot_id=s),
                             HintingRulesChecker(), inputs.roster, inputs.rules)
    row = child.demand_result.rows[0]
    assert (row.status, row.nurses_needed, row.note) == ("ok", 5, "set by manager (was missing)")


def test_bad_demand_changes_are_refused_before_anything_runs():
    old = _case()
    inputs = load_inputs()
    boom = lambda c, s: (_ for _ in ()).throw(AssertionError("scheduler must not be built"))
    ok = DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=4)
    for changes, message in (([], "No demand changes"), ([ok, ok], "More than one"),
                             ([DemandChange(unit="7W", date="2027-01-01", shift="day", nurses_needed=4)], "no demand row")):
        with pytest.raises(DecisionRefused, match=message):
            change_demand(old, changes, "case-2", boom, HintingRulesChecker(), inputs.roster, inputs.rules)
    with pytest.raises(ValueError):
        DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=-1)


# --- the case store ---------------------------------------------------------------


def test_store_round_trip_and_only_allowed_changes(tmp_path):
    store = CaseStore(tmp_path)
    rec = _case()
    store.save(rec)
    assert store.load("case-1") == rec and store.list_ids() == ["case-1"]
    store.save(approve(rec))
    assert store.load("case-1").state == "approved"
    with pytest.raises(CaseStoreError, match="cannot become"):
        store.save(reject(rec))  # a decided case on disk is never overwritten
    assert store.load("case-1").state == "approved"


def test_store_refuses_unsafe_ids_and_unreadable_files(tmp_path):
    store = CaseStore(tmp_path)
    for bad in ("../x", "a/b", "", ".hidden"):
        with pytest.raises(CaseStoreError, match="not a valid case id"):
            store.load(bad)
    with pytest.raises(CaseStoreError, match="no saved case"):
        store.load("nope")
    (tmp_path / "broken.json").write_text("{not json")
    with pytest.raises(CaseStoreError, match="could not be read"):
        store.load("broken")


def test_old_case_can_be_saved_as_out_of_date_after_change_demand(tmp_path):
    store, old = CaseStore(tmp_path), _case()
    store.save(old)
    inputs = load_inputs()
    retired, child = change_demand(old, [DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=5)],
                                   "case-2", lambda c, s: ScriptedScheduler([REFERENCE], case_id=c, snapshot_id=s),
                                   HintingRulesChecker(), inputs.roster, inputs.rules)
    store.save(retired)
    store.save(child)
    assert store.load("case-1").state == "out_of_date" and store.load("case-2").parent_case_id == "case-1"
