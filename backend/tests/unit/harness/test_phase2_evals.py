"""PRD eval cases 3, 8, 9, 11 and 12, and the other Phase 2 orchestrator rules. Scripted agents, no API calls."""

import json
from pathlib import Path

import pytest

from app.case_store import CaseStore, CaseStoreError
from app.contract.models import Draft
from app.decisions import DecisionRefused, approve, change_demand
from app.contract.case_record import DemandChange
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedAvailabilityAgent, ScriptedDemandAgent, ScriptedScheduler
from app.orchestrator import run_case, snapshot_id_for

WEEK = "2026-11-02"
REFERENCE = json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text())


def raw(name):
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


class CountingAgent:
    """Wraps a scripted agent and counts how many times it ran."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def run(self, snapshot):
        self.calls += 1
        return self.inner.run(snapshot)


class FlakyAgent(CountingAgent):
    """Fails the first `failures` times, then works."""

    def __init__(self, inner, failures):
        super().__init__(inner)
        self.failures = failures

    def run(self, snapshot):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("timed out")
        return self.inner.run(snapshot)


def go(demand=None, availability=None, scheduler=None, store=None, case_id="case-1"):
    inputs = load_inputs()
    demand = demand if demand is not None else ScriptedDemandAgent(raw("demand.json"))
    availability = availability if availability is not None else ScriptedAvailabilityAgent(raw("availability.json"))
    scheduler = scheduler or ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id_for(case_id))
    rec = run_case(demand, availability, scheduler, HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK,
                   case_id, store=store)
    return rec, scheduler


# --- eval 3: adversarial input ----------------------------------------------------------


def test_eval_3_one_empty_nurse_and_one_demand_error_are_listed_for_the_manager():
    demand = raw("demand.json")
    demand[3].update(patient_count=None, nurses_needed=None, flag="get_demand returned an error for this shift")
    availability = [r for r in raw("availability.json") if r["nurse_id"] != "N012"]
    rec, scheduler = go(ScriptedDemandAgent(demand), ScriptedAvailabilityAgent(availability))
    assert scheduler.calls == [] and rec.outcome == "stopped_missing_input" and rec.drafts == []
    assert [(n.item_type, n.id) for n in rec.needs_manual_review] == [("demand_day", "2026-11-03 night"), ("nurse", "N012")]
    assert "1 demand row(s) and 14 availability row(s)" in rec.stop_reason
    nothing_invented = [r for r in rec.availability_result.rows if r.nurse_id == "N012"]
    assert all(r.available is None and r.reason is None for r in nothing_invented)
    assert rec.demand_result.rows[3].nurses_needed is None


# --- eval 8: handoff failure ---------------------------------------------------------------


def test_eval_8_availability_times_out_so_it_is_retried_once_then_the_run_stops():
    always_fails = CountingAgent(ScriptedAvailabilityAgent(TimeoutError("timed out")))
    rec, scheduler = go(availability=always_fails)
    assert always_fails.calls == 2  # the first try and one retry
    assert scheduler.calls == [] and rec.outcome == "stopped_missing_input" and rec.drafts == []
    assert "336 availability row(s)" in rec.stop_reason and "after 2 tries" in rec.stop_reason


def test_eval_8_an_agent_that_returns_nothing_is_retried_once_then_the_run_stops():
    empty = CountingAgent(ScriptedAvailabilityAgent([]))
    rec, scheduler = go(availability=empty)
    assert empty.calls == 2 and scheduler.calls == [] and rec.outcome == "stopped_missing_input"
    assert "returned no rows" in rec.availability_result.rows[0].note


def test_a_retry_that_works_gives_a_normal_run():
    flaky = FlakyAgent(ScriptedAvailabilityAgent(raw("availability.json")), failures=1)
    rec, _ = go(availability=flaky)
    assert flaky.calls == 2 and rec.outcome == "passed"


# --- eval 9: malformed handoff ---------------------------------------------------------------


def test_eval_9_a_shift_outside_the_allowed_list_rejects_the_result_and_names_the_field():
    rows = raw("demand.json")
    rows[0]["shift"] = "evening"
    rec, scheduler = go(demand=ScriptedDemandAgent(rows))
    assert scheduler.calls == [] and rec.outcome == "stopped_missing_input"
    note = rec.demand_result.rows[0].note
    assert "rejected" in note and "row 1" in note and "field shift" in note
    assert rec.demand_result.counts.missing == 14  # nothing from the rejected result is used


def test_eval_9_a_row_with_a_missing_field_is_rejected_too():
    rows = raw("demand.json")
    del rows[1]["unit"]
    rec, scheduler = go(demand=ScriptedDemandAgent(rows))
    assert scheduler.calls == [] and "row 2, field unit" in rec.demand_result.rows[0].note


def test_an_availability_row_outside_the_allowed_reasons_is_rejected():
    rows = raw("availability.json")
    rows[5]["reason"] = "felt like it"
    rec, scheduler = go(availability=ScriptedAvailabilityAgent(rows))
    assert scheduler.calls == [] and "row 6, field reason" in rec.availability_result.rows[0].note


def test_a_result_that_is_not_a_list_is_rejected():
    class ReturnsADict:
        def run(self, snapshot):
            return {"rows": []}

    rec, scheduler = go(demand=ReturnsADict())
    assert scheduler.calls == [] and "not a list of rows" in rec.demand_result.rows[0].note


# --- eval 11: demand mismatch ------------------------------------------------------------------


def test_eval_11_four_nurses_for_a_five_nurse_shift_is_flagged_but_the_run_continues():
    rows = raw("demand.json")
    rows[0]["nurses_needed"] = 4  # 24 patients at 5 per nurse needs 5
    rec, _ = go(demand=ScriptedDemandAgent(rows))
    flagged = rec.demand_result.rows[0]
    assert (flagged.status, flagged.nurses_needed) == ("needs_review", 4) and "expected 5" in flagged.note
    assert rec.demand_result.counts.needs_review == 1 and rec.outcome != "stopped_missing_input"


# --- eval 12: demand outlier --------------------------------------------------------------------


def test_eval_12_wednesday_night_needing_9_when_other_nights_need_4_or_5_is_flagged():
    rows = raw("demand.json")
    wednesday = [r for r in rows if (r["date"], r["shift"]) == ("2026-11-04", "night")][0]
    wednesday.update(patient_count=45, nurses_needed=9)  # matches the ratio, so only the outlier rule applies
    rec, _ = go(demand=ScriptedDemandAgent(rows))
    row = [r for r in rec.demand_result.rows if (r.date, r.shift) == ("2026-11-04", "night")][0]
    assert (row.status, row.nurses_needed) == ("needs_review", 9) and "night-shift median" in row.note
    assert rec.demand_result.counts.needs_review == 1
    assert rec.drafts and rec.outcome != "stopped_missing_input"  # the draft is still built


def test_a_normal_week_has_no_outliers_and_a_small_difference_is_not_one():
    rows = raw("demand.json")
    assert go(demand=ScriptedDemandAgent(rows))[0].demand_result.counts.needs_review == 0


# --- the roster cross-check ---------------------------------------------------------------------


def test_a_nurse_in_availability_but_not_on_the_roster_is_reported_and_never_scheduled():
    rows = raw("availability.json") + [{"nurse_id": "N999", "date": WEEK, "shift": "day", "available": True,
                                         "reason": "none"}]
    rec, _ = go(availability=ScriptedAvailabilityAgent(rows))
    assert rec.outcome == "passed"
    review = [n for n in rec.needs_manual_review if n.id == "N999"]
    assert len(review) == 1 and review[0].item_type == "nurse" and "not on the roster" in review[0].note
    assert all(a.nurse_id != "N999" for a in rec.final_draft.assignments)


# --- saved after every status change -------------------------------------------------------------


def test_the_case_is_saved_as_building_before_the_agents_run_and_again_when_it_finishes(tmp_path):
    store = CaseStore(tmp_path)
    seen = []

    class Peek(ScriptedDemandAgent):
        def run(self, snapshot):
            seen.append(store.load("case-1").status)
            return super().run(snapshot)

    rec, _ = go(demand=Peek(raw("demand.json")), store=store)
    assert seen == ["building"]
    assert store.load("case-1") == rec and rec.status == "waiting_approval"


def test_a_stopped_run_is_saved_too_and_a_case_id_cannot_be_reused(tmp_path):
    store = CaseStore(tmp_path)
    rec, _ = go(availability=ScriptedAvailabilityAgent(TimeoutError("down")), store=store)
    assert store.load("case-1").outcome == "stopped_missing_input" == rec.outcome
    with pytest.raises(CaseStoreError, match="cannot become"):
        go(store=store)  # case-1 already exists


def test_store_update_saves_a_decision_and_a_refused_decision_saves_nothing(tmp_path):
    store = CaseStore(tmp_path)
    go(store=store)
    assert store.update("case-1", approve).status == "approved"
    assert store.load("case-1").manager_decision == "approved"
    stopped_store = CaseStore(tmp_path / "other")
    go(availability=ScriptedAvailabilityAgent(TimeoutError("down")), store=stopped_store, case_id="case-2")
    with pytest.raises(DecisionRefused):
        stopped_store.update("case-2", approve)
    assert stopped_store.load("case-2").status == "waiting_approval"


def test_change_demand_with_a_store_saves_the_new_case_and_retires_the_old_one(tmp_path):
    store = CaseStore(tmp_path)
    demand = raw("demand.json")
    demand[0].update(patient_count=None, nurses_needed=None, flag="no data")
    old, _ = go(demand=ScriptedDemandAgent(demand), store=store)
    assert old.outcome == "stopped_missing_input"
    inputs = load_inputs()
    retired, child = change_demand(
        old, [DemandChange(unit="7W", date=WEEK, shift="day", nurses_needed=5)], "case-2",
        lambda c, s: ScriptedScheduler([REFERENCE], case_id=c, snapshot_id=s), HintingRulesChecker(),
        inputs.roster, inputs.rules, store=store)
    assert store.load("case-1").status == "out_of_date" and store.load("case-2") == child
    assert child.outcome == "passed"
