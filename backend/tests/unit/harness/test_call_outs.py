"""Late call-outs (PRD eval cases 2 and 10): locked assignments, the out_of_date parent, and the checks in code."""

import json
from pathlib import Path

import pytest

from app.callouts import run_call_out
from app.case_store import CaseStore
from app.contract.models import Callout, Draft
from app.decisions import DecisionRefused, approve, reject
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedAvailabilityAgent, ScriptedDemandAgent, ScriptedScheduler
from app.orchestrator import run_case, snapshot_id_for

WEEK = "2026-11-02"
REFERENCE = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))
CALL = Callout(nurse_id="N006", date="2026-11-04", shift="day", reported_at="2026-11-03T22:15:00")


def raw(name):
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def parent_case(store=None, availability=None, case_id="case-1"):
    inputs = load_inputs()
    return run_case(
        ScriptedDemandAgent(raw("demand.json")),
        ScriptedAvailabilityAgent(availability if availability is not None else raw("availability.json")),
        ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id_for(case_id)),
        HintingRulesChecker(), inputs.roster, inputs.rules, "7W", WEEK, case_id, store=store)


def swapped(draft, date, shift, old, new):
    """The draft with `new` working the shift `old` was on."""
    return draft.model_copy(update={"assignments": [
        a.model_copy(update={"nurse_id": new}) if (a.nurse_id, a.date, a.shift) == (old, date, shift) else a
        for a in draft.assignments]})


class Recording(ScriptedScheduler):
    """Remembers the inputs it was given."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.inputs = []

    def build(self, version, inputs, previous_draft, violations):
        self.inputs.append(inputs)
        return super().build(version, inputs, previous_draft, violations)


def call_out(parent, callouts, drafts, new_case_id="case-2", store=None, scheduler_cls=ScriptedScheduler):
    made = []

    def factory(case_id, snapshot_id):
        made.append(scheduler_cls(drafts, case_id=case_id, snapshot_id=snapshot_id))
        return made[-1]

    inputs = load_inputs()
    old, child = run_call_out(parent, callouts, new_case_id, factory, HintingRulesChecker(), inputs.roster,
                              inputs.rules, store=store)
    return old, child, made[0]


GOOD = swapped(REFERENCE, "2026-11-04", "day", "N006", "N002")


# --- eval 10: late call-out ----------------------------------------------------------------


def test_eval_10_late_call_out_marks_the_old_case_out_of_date_and_reruns_the_affected_shift():
    parent = parent_case()
    old, child, scheduler = call_out(parent, [CALL], [GOOD], scheduler_cls=Recording)
    assert (old.status, old.newer_case_id) == ("out_of_date", "case-2")
    assert (child.trigger, child.parent_case_id, child.status, child.outcome) == ("call_out", "case-1", "waiting_approval", "passed")
    assert [(s.date, s.shift) for s in child.affected_shifts] == [("2026-11-04", "day")]
    assert child.snapshot_id == "snap-case-2" != parent.snapshot_id
    assert [(c.nurse_id, c.reported_at) for c in child.callouts] == [("N006", "2026-11-03T22:15:00")]
    on_shift = sorted(a.nurse_id for a in child.final_draft.assignments if (a.date, a.shift) == ("2026-11-04", "day"))
    assert on_shift == ["N001", "N002", "N005", "N012", "N015"]


def test_the_manager_cannot_approve_the_out_of_date_case():
    old, _, _ = call_out(parent_case(), [CALL], [GOOD])
    with pytest.raises(DecisionRefused, match="out of date.*case-2"):
        approve(old)
    with pytest.raises(DecisionRefused):
        reject(old)


def test_the_called_out_nurse_is_unavailable_and_the_rest_of_the_week_is_locked():
    parent = parent_case()
    _, child, scheduler = call_out(parent, [CALL], [GOOD], scheduler_cls=Recording)
    row = [r for r in child.availability_result.rows if (r.nurse_id, r.date, r.shift) == ("N006", "2026-11-04", "day")][0]
    assert (row.available, row.reason, row.status) == (False, "call_out", "ok") and "22:15" in row.note
    seen = scheduler.inputs[0]
    in_affected = [a for a in REFERENCE.assignments if (a.date, a.shift) == ("2026-11-04", "day")]
    assert len(seen.locked_assignments) == len(REFERENCE.assignments) - len(in_affected)
    assert all((a.date, a.shift) != ("2026-11-04", "day") for a in seen.locked_assignments)
    assert sorted(a.nurse_id for a in seen.earlier_assignments) == ["N001", "N005", "N012", "N015"]  # not N006
    assert len(child.availability_result.rows) == len(parent.availability_result.rows)
    other = [r for r in child.availability_result.rows if r.nurse_id != "N006" or r.date != "2026-11-04"]
    assert all(r.status == "ok" and r.reason != "call_out" for r in other)


def test_the_parent_record_is_not_changed_in_place():
    parent = parent_case()
    call_out(parent, [CALL], [GOOD])
    assert parent.status == "waiting_approval" and parent.newer_case_id is None
    assert [r.reason for r in parent.availability_result.rows if r.reason == "call_out"] == []


# --- code checks the Scheduler cannot skip ---------------------------------------------------


def test_a_draft_that_changes_a_locked_assignment_fails_the_round():
    sneaky = swapped(GOOD, "2026-11-02", "day", "N008", "N003")  # a locked shift
    _, child, _ = call_out(parent_case(), [CALL], [sneaky])
    assert child.outcome == "stopped_after_3_rounds" and child.final_draft is None and child.drafts == []
    assert all("changed locked assignments" in r.error and "N008" in r.error for r in child.rounds)


def test_a_draft_that_drops_a_locked_assignment_fails_too():
    short = GOOD.model_copy(update={"assignments": [a for a in GOOD.assignments
                                                      if (a.nurse_id, a.date, a.shift) != ("N008", "2026-11-02", "day")]})
    _, child, _ = call_out(parent_case(), [CALL], [short])
    assert child.drafts == [] and "1 removed" in child.rounds[0].error


def test_a_fix_round_can_still_repair_the_affected_shift():
    still_has_caller = REFERENCE  # N006 is still on the shift they called out of
    _, child, _ = call_out(parent_case(), [CALL], [still_has_caller, GOOD])
    assert (child.outcome, child.rounds_used) == ("passed", 2)
    first = [v for vv in child.violations if vv.version == 1 for v in vv.violations]
    assert [(v.rule, v.nurse_id) for v in first] == [("availability", "N006")]


def test_suggestions_must_name_a_roster_nurse_and_an_affected_shift():
    from app.contract.models import Suggestion
    for bad, text in ((Suggestion(date="2026-11-04", shift="day", nurse_id="N999", reason="x"), "not on the roster"),
                      (Suggestion(date="2026-11-06", shift="night", nurse_id="N002", reason="x"), "not an affected shift")):
        _, child, _ = call_out(parent_case(), [CALL], [GOOD.model_copy(update={"suggestions": [bad]})])
        assert child.drafts == [] and text in child.rounds[0].error


def test_a_valid_suggestion_is_kept_for_the_manager():
    from app.contract.models import Suggestion
    suggestion = Suggestion(date="2026-11-04", shift="day", nurse_id="N002", reason="N002 is free and certified.")
    _, child, _ = call_out(parent_case(), [CALL], [GOOD.model_copy(update={"suggestions": [suggestion]})])
    assert child.final_draft.suggestions == [suggestion]


# --- refusals ------------------------------------------------------------------------------------


def test_a_call_out_is_refused_when_it_cannot_be_applied_and_nothing_is_saved(tmp_path):
    store = CaseStore(tmp_path)
    parent = parent_case(store=store)
    bad = [([], "No call-outs"),
           ([CALL.model_copy(update={"nurse_id": "N999"})], "not on the roster"),
           ([CALL.model_copy(update={"date": "2026-12-25"})], "outside the week")]
    for callouts, text in bad:
        with pytest.raises(DecisionRefused, match=text):
            call_out(parent, callouts, [GOOD], store=store)
    assert store.list_ids() == ["case-1"] and store.load("case-1").status == "waiting_approval"


def test_decided_stopped_and_out_of_date_cases_cannot_take_a_call_out():
    decided = approve(parent_case())
    with pytest.raises(DecisionRefused, match="already approved"):
        call_out(decided, [CALL], [GOOD])
    stopped = parent_case(availability=[])  # an agent that returns nothing, twice: the run stops before scheduling
    assert stopped.outcome == "stopped_missing_input" and stopped.final_draft is None
    with pytest.raises(DecisionRefused, match="no draft to update"):
        call_out(stopped, [CALL], [GOOD])
    old, _, _ = call_out(parent_case(), [CALL], [GOOD])
    with pytest.raises(DecisionRefused, match="out of date"):
        call_out(old, [CALL], [GOOD], new_case_id="case-3")


def test_two_call_outs_list_both_shifts_in_order_and_a_repeat_is_ignored():
    second = Callout(nurse_id="N003", date="2026-11-03", shift="night", reported_at="2026-11-03T23:00:00")
    parent = parent_case()
    drafts = [REFERENCE]  # not checked here: only the setup is
    _, child, scheduler = call_out(parent, [CALL, second, CALL], drafts, scheduler_cls=Recording)
    assert [(s.date, s.shift) for s in child.affected_shifts] == [("2026-11-03", "night"), ("2026-11-04", "day")]
    assert len(child.callouts) == 2
    assert all((a.date, a.shift) not in {("2026-11-03", "night"), ("2026-11-04", "day")}
               for a in scheduler.inputs[0].locked_assignments)


# --- saved on every status change -----------------------------------------------------------------


def test_the_new_case_is_saved_building_then_finished_and_the_old_case_is_saved_out_of_date(tmp_path):
    store = CaseStore(tmp_path)
    parent = parent_case(store=store)
    seen = []

    class Peek(ScriptedScheduler):
        def build(self, version, inputs, previous_draft, violations):
            seen.append((store.load("case-2").status, store.load("case-1").status))
            return super().build(version, inputs, previous_draft, violations)

    old, child, _ = call_out(parent, [CALL], [GOOD], store=store, scheduler_cls=Peek)
    assert seen == [("building", "waiting_approval")]  # the old case is retired only after the new one finishes
    assert store.load("case-1") == old and store.load("case-2") == child


# --- eval 2: edge case --------------------------------------------------------------------------------


def test_eval_2_two_on_leave_and_one_call_out_leave_exact_gaps_and_a_replacement_option():
    from app.contract.models import OpenGap, Suggestion
    working = {a.nurse_id for a in REFERENCE.assignments if (a.date, a.shift) == ("2026-11-04", "day")}
    free = [n.nurse_id for n in load_inputs().roster if n.nurse_id not in working]
    rows = raw("availability.json")
    for r in rows:
        if (r["date"], r["shift"]) == ("2026-11-04", "day") and r["nurse_id"] in free:
            on_leave = r["nurse_id"] in free[:2]
            r.update(available=False, reason="approved_time_off" if on_leave else "none")
    parent = parent_case(availability=rows)
    callouts = [CALL, Callout(nurse_id="N003", date="2026-11-05", shift="day", reported_at="2026-11-04T06:00:00")]
    # 11-04 day: nobody is left to cover N006, so that shift stays one short. 11-05 day: N002 can cover N003.
    draft = swapped(REFERENCE, "2026-11-05", "day", "N003", "N002")
    draft = draft.model_copy(update={
        "assignments": [a for a in draft.assignments if (a.nurse_id, a.date, a.shift) != ("N006", "2026-11-04", "day")],
        "open_gaps": [OpenGap(unit="7W", date="2026-11-04", shift="day", nurses_needed=5, nurses_assigned=4,
                              gap_reason="no_available_nurse")],
        "suggestions": [Suggestion(date="2026-11-05", shift="day", nurse_id="N002", reason="N002 is free and certified.")],
    })
    _, child, _ = call_out(parent, callouts, [draft])
    assert child.outcome == "stopped_after_3_rounds"  # the gap is a hard coverage violation, so it is not "passing"
    assert [(v.rule, v.date, v.shift) for v in child.open_violations] == [("coverage", "2026-11-04", "day")]
    assert [(g.date, g.shift, g.nurses_needed, g.nurses_assigned) for g in child.final_draft.open_gaps] == [("2026-11-04", "day", 5, 4)]
    assert [(s.date, s.nurse_id) for s in child.final_draft.suggestions] == [("2026-11-05", "N002")]
    assert len(child.affected_shifts) == 2


# --- get_callouts ------------------------------------------------------------------------------------------


def test_get_callouts_reads_the_folders_file_for_the_roster_and_week_only(tmp_path):
    from app.agents.data_source import MockSource
    from app.orchestrator import make_snapshot
    inputs = load_inputs()
    snapshot = make_snapshot(inputs.roster, inputs.rules, "7W", WEEK, "snap-x")
    assert MockSource(DEFAULT_DATA).get_callouts(snapshot) == []  # the base mock week has no call-outs
    rows = [{"nurse_id": "N006", "date": "2026-11-04", "shift": "day", "reported_at": "2026-11-03T22:15:00"},
            {"nurse_id": "N999", "date": "2026-11-04", "shift": "day", "reported_at": "2026-11-03T22:15:00"},
            {"nurse_id": "N006", "date": "2026-12-25", "shift": "day", "reported_at": "2026-11-03T22:15:00"}]
    (tmp_path / "callouts.json").write_text(json.dumps(rows))
    assert MockSource(tmp_path).get_callouts(snapshot) == rows[:1]
