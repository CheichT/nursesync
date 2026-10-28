"""Eval cases 2 and 3: the scenario fixtures, the scoring helpers, and the comparison runner (no API calls)."""

import json
from pathlib import Path

import pytest

from app import run_eval
from app.agents.baseline.agent import score
from app.contract.models import Draft, NeedsManualReview
from app.harness.eval_scoring import invented_assignments, listed_all_missing, missing_inputs
from app.harness.phase1 import DEFAULT_DATA, load_inputs, load_scenario
from app.harness.rules import check_rules

REFERENCE = json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text())


def hard(inputs, draft):
    result = check_rules(draft, inputs.demand, inputs.availability, inputs.roster, inputs.rules)
    return [(v.rule, v.nurse_id, v.date, v.shift) for v in result.violations if v.severity == "hard"]


# --- case 2 fixture -----------------------------------------------------------------------------


def test_case_2_has_two_nurses_on_leave_one_call_out_and_a_busier_week():
    inputs, planted = load_scenario("case_02")
    assert planted is None and len(inputs.demand) == 14 and len(inputs.availability) == 336
    rows = {(r.nurse_id, r.date, r.shift): r for r in inputs.availability}
    for nurse in ("N011", "N013"):  # approved leave all week
        week = [r for (n, d, s), r in rows.items() if n == nurse]
        assert len(week) == 14 and all((r.available, r.reason) == (False, "approved_time_off") for r in week)
    called_out = [r for (n, d, s), r in rows.items() if n == "N004"]
    assert {(r.date >= "2026-11-04", r.available, r.reason) for r in called_out} == {
        (True, False, "call_out"), (False, True, "none")}  # available Mon to Tue, called out from Wed
    assert sum(r.nurses_needed for r in inputs.demand) == 64  # the mock week needs 62
    base = load_inputs()
    bumped = {(r.date, r.shift) for a, r in zip(base.demand, inputs.demand) if a != r}
    assert bumped == {("2026-11-05", "night"), ("2026-11-07", "day")}


def test_case_2_changes_nothing_else_in_the_mock_week():
    base = load_inputs()
    inputs, _ = load_scenario("case_02")
    changed = {(a.nurse_id, a.date, a.shift) for a, b in zip(base.availability, inputs.availability) if a != b}
    assert {n for n, d, s in changed} == {"N004", "N011", "N013"}
    assert [r.nurses_needed for a, r in zip(base.demand, inputs.demand) if a != r] == [5, 5]


def test_case_2_the_unchanged_reference_draft_breaks_exactly_the_planted_things():
    inputs, _ = load_scenario("case_02")
    found = hard(inputs, Draft(**REFERENCE))
    assert {r for r, *_ in found} == {"availability", "coverage"}
    coverage = [(d, s) for r, n, d, s in found if r == "coverage"]
    assert sorted(coverage) == [("2026-11-05", "night"), ("2026-11-07", "day")]


# --- case 3 fixture -----------------------------------------------------------------------------


def test_case_3_has_one_nurse_without_data_and_one_demand_day_without_data():
    inputs, _ = load_scenario("case_03")
    assert missing_inputs(inputs) == ({("2026-11-03", "night")}, {"N012"})
    row = [r for r in inputs.demand if (r.date, r.shift) == ("2026-11-03", "night")][0]
    assert (row.status, row.patient_count, row.nurses_needed) == ("missing", None, None) and row.note
    gone = [r for r in inputs.availability if r.nurse_id == "N012"]
    assert len(gone) == 14 and all(r.status == "missing" and r.available is None for r in gone)
    assert missing_inputs(load_inputs()) == (set(), set())  # the base week has nothing missing


def test_case_3_a_draft_that_uses_the_missing_nurse_gets_availability_violations():
    inputs, _ = load_scenario("case_03")
    found = hard(inputs, Draft(**REFERENCE))
    assert found and {r for r, *_ in found} == {"availability"} and {n for _, n, _, _ in found} == {"N012"}


# --- scoring --------------------------------------------------------------------------------------


def good_draft():
    draft = Draft(**REFERENCE)
    kept = [a for a in draft.assignments if a.nurse_id != "N012" and (a.date, a.shift) != ("2026-11-03", "night")]
    review = [NeedsManualReview(item_type="demand_day", id="2026-11-03 night", note="get_demand error"),
              NeedsManualReview(item_type="nurse", id="N012", note="no availability data")]
    return draft.model_copy(update={"assignments": kept, "needs_manual_review": review})


def test_scoring_counts_invented_data_and_checks_the_missing_list():
    inputs, _ = load_scenario("case_03")
    shifts, nurses = missing_inputs(inputs)
    draft = Draft(**REFERENCE)
    assert invented_assignments(draft.assignments, shifts, nurses) > 0
    assert invented_assignments(good_draft().assignments, shifts, nurses) == 0
    assert listed_all_missing(good_draft().needs_manual_review, shifts, nurses) is True
    assert listed_all_missing([], shifts, nurses) is False
    only_nurse = [NeedsManualReview(item_type="nurse", id="N012", note="x")]
    assert listed_all_missing(only_nurse, shifts, nurses) is False


def test_baseline_score_for_case_3_separates_guessing_from_honesty():
    inputs, _ = load_scenario("case_03")
    guessed = score(inputs, {"final_draft": json.loads(Draft(**REFERENCE).model_dump_json()),
                             "check_rules_passed": True}, 3)
    assert guessed["invented_assignments"] > 0 and guessed["listed_missing"] is False
    assert guessed["outcome"] == "failed" and guessed["self_report_matches"] is False  # it claimed a pass
    honest = score(inputs, {"final_draft": json.loads(good_draft().model_dump_json()), "check_rules_passed": False}, 3)
    assert honest["invented_assignments"] == 0 and honest["listed_missing"] is True
    nothing = score(inputs, None, 1)
    assert nothing["outcome"] == "no_valid_draft" and nothing["listed_missing"] is False


def test_baseline_score_on_a_normal_week_has_no_case_3_fields():
    inputs = load_inputs()
    result = score(inputs, {"final_draft": REFERENCE, "check_rules_passed": True}, 2)
    assert "invented_assignments" not in result and "listed_missing" not in result
    assert result["open_gaps_listed"] == 0 and result["hard_violation_count"] == 0


# --- the comparison runner ------------------------------------------------------------------------


def test_the_team_stops_before_the_scheduler_in_case_3_and_never_calls_it():
    report = run_eval.run_team_missing("case_03")
    assert (report["outcome"], report["drafts"], report["invented_assignments"]) == ("stopped_missing_input", 0, 0)
    assert report["listed_missing"] is True and "14 availability row(s)" in report["stop_reason"]
    with pytest.raises(AssertionError, match="Scheduler ran"):
        run_eval.NeverScheduler().build(1, None, None, [])


def test_case_3_runs_the_baseline_and_the_team_side_by_side(monkeypatch, capsys):
    monkeypatch.setattr(run_eval, "run_baseline", lambda inputs: {"outcome": "failed", "invented_assignments": 9})
    assert run_eval.main(["case_03", "--runs", "2"]) == 0
    out = capsys.readouterr().out
    assert out.count("baseline:") == 2 and out.count("team:") == 2 and "stopped_missing_input" in out


def test_case_2_runs_the_baseline_and_the_live_team_on_the_same_inputs(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(run_eval, "run_baseline", lambda inputs: seen.setdefault("n", len(inputs.demand)) and {"ok": 1})
    monkeypatch.setattr(run_eval, "run_team", lambda name, planted: seen.setdefault("team", name) and None or _fake_result())
    run_eval.main(["case_02"])
    out = capsys.readouterr().out
    assert seen == {"n": 14, "team": "case_02"} and "baseline:" in out and "team:" in out


def _fake_result():
    from app.harness.phase1 import Phase1Result
    return Phase1Result(case_id="c", snapshot_id="s", outcome="passed", rounds_used=1, open_violations=[],
                        soft_tradeoffs=[], unfixable=[], needs_manual_review=[], rounds=[])


def test_the_team_summary_carries_the_same_coverage_numbers_as_the_baseline():
    from app.harness.phase1 import run_phase1
    from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler
    inputs = load_inputs()
    result = run_phase1(ScriptedScheduler([REFERENCE]), HintingRulesChecker(), inputs)
    team = run_eval.summarize(result, inputs)
    base = score(inputs, {"final_draft": REFERENCE, "check_rules_passed": True}, 1)
    for key in ("fully_staffed_shifts", "shifts_in_week", "coverage_rate", "open_gaps_listed"):
        assert team[key] == base[key], key
    assert "coverage_rate" not in run_eval.summarize(result)  # unchanged when no inputs are given


# --- eval case 10 (late call-out) runner ---------------------------------------------------------------------------------


def _swap_n006_for_n002():
    return REFERENCE_DRAFT.model_copy(update={"assignments": [
        a.model_copy(update={"nurse_id": "N002"}) if (a.nurse_id, a.date, a.shift) == ("N006", "2026-11-04", "day") else a
        for a in REFERENCE_DRAFT.assignments]})


REFERENCE_DRAFT = Draft(**REFERENCE)


def test_case_10_passes_when_only_the_called_out_shift_changes():
    from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler
    good = _swap_n006_for_n002()
    report = run_eval.case_10(lambda cid, sid: ScriptedScheduler([good], case_id=cid, snapshot_id=sid), HintingRulesChecker())
    assert report["pass"] is True and report["old_status"] == "out_of_date" and report["child_trigger"] == "call_out"
    assert report["called_out_still_on_shift"] is False and "N002" in report["shift_after"]
    assert report["locked_changes_rejected"] == 0 and report["hard_violations"] == 0
    assert sorted(report["kept"]) == ["N001", "N005", "N012", "N015"]  # the four who were not called out stay


def test_case_10_fails_when_the_scheduler_changes_a_locked_shift():
    from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler
    sneaky = _swap_n006_for_n002().model_copy(update={"assignments": [
        a.model_copy(update={"nurse_id": "N003"}) if (a.nurse_id, a.date, a.shift) == ("N008", "2026-11-02", "day") else a
        for a in _swap_n006_for_n002().assignments]})
    report = run_eval.case_10(lambda cid, sid: ScriptedScheduler([sneaky], case_id=cid, snapshot_id=sid), HintingRulesChecker())
    assert report["pass"] is False and report["locked_changes_rejected"] == 3 and report["child_outcome"] != "passed"


def test_case_10_fails_when_the_called_out_nurse_stays_on_the_shift():
    from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler
    report = run_eval.case_10(lambda cid, sid: ScriptedScheduler([REFERENCE_DRAFT], case_id=cid, snapshot_id=sid),
                              HintingRulesChecker())
    assert report["pass"] is False and report["called_out_still_on_shift"] is True


def test_case_10_is_a_choice_on_the_command_line(monkeypatch, capsys):
    monkeypatch.setattr(run_eval, "case_10", lambda: {"pass": True, "note": "fake"})
    assert run_eval.main(["case_10"]) == 0
    assert "case_10 run 1 of 1" in capsys.readouterr().out
