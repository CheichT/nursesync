"""The agents' advisory extras (`unusual` and `needs_manual_review`) are cleaned, saved in the case record, and
inherited by child cases. They never change a row's status and never stop a run."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_output import AgentOutput, clean_notes, clean_review, merge_review
from app.callouts import run_call_out
from app.case_store import CaseStore
from app.contract.case_record import CaseRecord, DemandChange
from app.contract.models import Callout, Draft, NeedsManualReview
from app.decisions import change_demand
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedAvailabilityAgent, ScriptedDemandAgent, ScriptedScheduler
from app.orchestrator import make_snapshot, run_case, snapshot_id_for

REFERENCE = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
WEEK = "2026-11-02"
DAY = {"item_type": "demand_day", "id": "2026-11-06 night", "note": "Census may rise."}
NURSE = {"item_type": "nurse", "id": "N010", "note": "Partial data for this nurse."}


def raw(name):
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def go(demand=None, availability=None, case_id="case-1", store=None):
    inputs = load_inputs()
    return run_case(demand or ScriptedDemandAgent(raw("demand.json")),
                    availability or ScriptedAvailabilityAgent(raw("availability.json")),
                    ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id_for(case_id)),
                    HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK, case_id, store=store)


def with_extras(unusual=None, demand_review=None, availability_review=None, **kw):
    return go(ScriptedDemandAgent(raw("demand.json"), unusual if unusual is not None else [], demand_review or []),
              ScriptedAvailabilityAgent(raw("availability.json"), None, availability_review or []), **kw)


# --- saved in the record ----------------------------------------------------------------------------------------


def test_extras_are_saved_and_the_review_items_are_merged_into_needs_manual_review():
    rec = with_extras(["Friday night is the busiest."], [DAY], [NURSE])
    assert rec.unusual == ["Friday night is the busiest."]
    assert [(n.item_type, n.id) for n in rec.input_review] == [("demand_day", "2026-11-06 night"), ("nurse", "N010")]
    assert [(n.item_type, n.id) for n in rec.needs_manual_review] == [("demand_day", "2026-11-06 night"), ("nurse", "N010")]
    assert rec.outcome == "passed"


def test_a_run_with_plain_row_lists_has_empty_extras():
    rec = go()
    assert rec.unusual == [] and rec.input_review == [] and rec.needs_manual_review == []


def test_extras_never_change_a_row_status_or_stop_a_run():
    everyone = [{"item_type": "nurse", "id": f"N{i:03d}", "note": "look at this"} for i in range(1, 25)]
    rec = with_extras(["Everything looks odd."], [DAY], everyone)
    assert rec.outcome == "passed" and rec.status == "waiting_approval"
    assert rec.demand_result.counts.ok == 14 and rec.availability_result.counts.ok == 336  # statuses are code's alone


def test_a_failed_agent_saves_no_extras():
    rec = go(availability=ScriptedAvailabilityAgent(TimeoutError("down"), None, [NURSE]))
    assert rec.outcome == "stopped_missing_input" and rec.input_review == []


def test_a_retry_keeps_the_extras_of_the_try_that_worked():
    class FlakyWithExtras(ScriptedDemandAgent):
        calls = 0

        def run(self, snapshot):
            FlakyWithExtras.calls += 1
            if FlakyWithExtras.calls == 1:
                raise TimeoutError("timed out")
            return super().run(snapshot)

    rec = go(demand=FlakyWithExtras(raw("demand.json"), ["Second try note."], [DAY]))
    assert FlakyWithExtras.calls == 2 and rec.unusual == ["Second try note."] and len(rec.input_review) == 1


def test_a_nurse_not_on_the_roster_and_the_agents_items_are_both_kept_without_repeats():
    rows = raw("availability.json") + [{"nurse_id": "N999", "date": WEEK, "shift": "day", "available": True, "reason": "none"}]
    rec = go(availability=ScriptedAvailabilityAgent(rows, None, [NURSE, {"item_type": "nurse", "id": "N999", "note": "agent also mentions it"}]))
    ids = [(n.item_type, n.id) for n in rec.input_review]
    assert ids == [("nurse", "N999"), ("nurse", "N010")]  # code's item first; the agent's repeat of N999 is dropped
    assert "not on the roster" in rec.input_review[0].note


def test_in_a_stopped_run_the_agents_repeat_of_a_missing_item_appears_once_with_codes_note():
    demand = raw("demand.json")
    demand[3].update(patient_count=None, nurses_needed=None, flag="get_demand error")
    rec = go(demand=ScriptedDemandAgent(demand, [], [{"item_type": "demand_day", "id": "2026-11-03 night", "note": "agent words"}]))
    assert rec.outcome == "stopped_missing_input"
    same = [n for n in rec.needs_manual_review if n.id == "2026-11-03 night"]
    assert len(same) == 1 and "agent words" not in same[0].note  # code's own note wins
    assert [n.id for n in rec.input_review] == ["2026-11-03 night"]  # the agent's item is still in input_review


# --- cleaning -----------------------------------------------------------------------------------------------------------


def test_notes_are_one_clean_short_line_each_and_capped():
    rec = with_extras(["line one\nline two\x00\x1b[31m red", "x" * 1000, 42, None, "", "   "] + [f"note {i}" for i in range(30)])
    assert "\n" not in rec.unusual[0] and "\x00" not in rec.unusual[0] and "\x1b" not in rec.unusual[0]
    assert len(rec.unusual[1]) == 300 and rec.unusual[1].endswith("…")
    assert len(rec.unusual) == 20 and all(isinstance(n, str) and n for n in rec.unusual)


def test_malformed_review_items_are_dropped_and_the_rows_are_untouched():
    bad = [{"item_type": "shift", "id": "x", "note": "wrong type"}, {"item_type": "nurse", "note": "no id"},
           {"item_type": "nurse", "id": "N003"}, {"item_type": "nurse", "id": 5, "note": "id not text"},
           "not a dict", None, NURSE]
    rec = with_extras(None, bad, None)
    assert [n.id for n in rec.input_review] == ["N010"] and rec.outcome == "passed"
    assert clean_review("not a list") == [] and clean_notes({"a": 1}) == []


def test_review_notes_and_ids_are_length_capped_and_one_line():
    item = {"item_type": "nurse", "id": "N0\n10", "note": "n" * 900}
    kept = clean_review([item])
    assert kept[0].id == "N0 10" and len(kept[0].note) == 300


def test_merge_review_keeps_the_first_of_each_item_and_the_order():
    a = NeedsManualReview(item_type="nurse", id="N1", note="mine")
    b = NeedsManualReview(item_type="nurse", id="N1", note="theirs")
    c = NeedsManualReview(item_type="demand_day", id="N1", note="same id, other type")
    assert [(n.item_type, n.note) for n in merge_review([a], [b, c])] == [("nurse", "mine"), ("demand_day", "same id, other type")]


# --- children inherit them ---------------------------------------------------------------------------------------------------


def waiting_with_extras(store, unusual=("Friday is busy.",)):
    return with_extras(list(unusual), [DAY, {"item_type": "demand_day", "id": "2026-11-02 day", "note": "Monday check."}],
                       [NURSE], store=store)


def test_change_demand_inherits_the_extras_except_for_the_day_the_manager_set(tmp_path):
    store = CaseStore(tmp_path)
    old = waiting_with_extras(store)
    inputs = load_inputs()
    _, child = change_demand(old, [DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=5)], "case-2",
                             lambda c, s: ScriptedScheduler([REFERENCE], case_id=c, snapshot_id=s), HintingRulesChecker(),
                             inputs.roster, inputs.rules, store=store)
    assert child.unusual == ["Friday is busy."]
    assert sorted((n.item_type, n.id) for n in child.input_review) == [("demand_day", "2026-11-06 night"), ("nurse", "N010")]
    assert "2026-11-02 day" not in [n.id for n in child.needs_manual_review]  # the manager gave Monday day a number
    assert store.load("case-2").input_review == child.input_review


def test_a_call_out_child_inherits_all_of_the_extras(tmp_path):
    old = waiting_with_extras(None)
    inputs = load_inputs()
    good = REFERENCE.model_copy(update={"assignments": [
        a.model_copy(update={"nurse_id": "N002"}) if (a.nurse_id, a.date, a.shift) == ("N006", "2026-11-04", "day") else a
        for a in REFERENCE.assignments]})
    call = Callout(nurse_id="N006", date="2026-11-04", shift="day", reported_at="2026-11-03T22:15:00")
    _, child = run_call_out(old, [call], "case-2", lambda c, s: ScriptedScheduler([good], case_id=c, snapshot_id=s),
                            HintingRulesChecker(), inputs.roster, inputs.rules)
    assert child.unusual == old.unusual and child.input_review == old.input_review


# --- the live agents hand the extras back --------------------------------------------------------------------------------------


def text(t):
    return SimpleNamespace(type="text", text=t)


class FakeClient:
    def __init__(self, reply):
        self.reply, self.messages = reply, self

    def create(self, **kwargs):
        return SimpleNamespace(content=[text(self.reply)], stop_reason="end_turn")


def test_the_live_agents_return_their_extras_and_the_orchestrator_saves_them():
    from app.agents.availability.agent import AnthropicAvailabilityAgent
    from app.agents.data_source import MockSource
    from app.agents.demand.agent import AnthropicDemandAgent
    demand_rows = [{**{k: r[k] for k in ("unit", "date", "shift", "patient_count", "nurses_needed")}, "note": ""}
                   for r in json.loads((Path(DEFAULT_DATA) / "demand.json").read_text())]
    avail_rows = [{**{k: r[k] for k in ("nurse_id", "date", "shift", "available", "reason")}, "note": ""}
                  for r in json.loads((Path(DEFAULT_DATA) / "availability.json").read_text())]
    demand = AnthropicDemandAgent(client=FakeClient(json.dumps(
        {"rows": demand_rows, "unusual": ["Saturday is quiet."], "needs_manual_review": [DAY]})), source=MockSource(DEFAULT_DATA))
    avail = AnthropicAvailabilityAgent(client=FakeClient(json.dumps(
        {"rows": avail_rows, "needs_manual_review": [NURSE]})), source=MockSource(DEFAULT_DATA))
    inputs = load_inputs()
    out = demand.run(make_snapshot(inputs.roster, inputs.rules, "7W", WEEK, "snap-x"))
    assert isinstance(out, AgentOutput) and out.unusual == ["Saturday is quiet."] and out.needs_manual_review == [DAY]
    rec = go(demand, avail)
    assert rec.unusual == ["Saturday is quiet."] and [n.id for n in rec.input_review] == ["2026-11-06 night", "N010"]
    assert rec.outcome == "passed"


# --- compatibility ---------------------------------------------------------------------------------------------------------------


def test_an_older_record_without_the_new_fields_still_loads():
    record = json.loads(go().model_dump_json())
    del record["unusual"], record["input_review"]
    loaded = CaseRecord.model_validate(record)
    assert loaded.unusual == [] and loaded.input_review == []
