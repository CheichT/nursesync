"""Tests for the Phase 1 harness loop, using scripted stand-in agents (no AI, no API key).

Owner: Cheich. The loop is judged by check_rules in code. These tests check that the loop
follows the PRD: up to 3 rounds, the code's list wins, and nothing missing or broken is ever
treated as a pass.
"""

import json
from pathlib import Path

import pytest

from app.contract.models import Draft
from app.harness.phase1 import format_report, load_inputs, main, run_phase1
from app.harness.stand_ins import (
    CrashingRulesChecker,
    DroppingRulesChecker,
    HintingRulesChecker,
    InventingRulesChecker,
    ScriptedScheduler,
    without,
    without_shifts,
)

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"


@pytest.fixture(scope="module")
def inputs():
    return load_inputs(MOCK)


@pytest.fixture
def reference():
    return Draft(**json.loads((MOCK / "reference_draft.json").read_text()))


def hard_rules(violations):
    return sorted(v.rule for v in violations)


# --- the loop ----------------------------------------------------------------------


def test_good_first_draft_passes_in_one_round_and_the_checker_is_not_called(inputs, reference):
    scheduler, checker = ScriptedScheduler([reference]), HintingRulesChecker()
    result = run_phase1(scheduler, checker, inputs)
    assert result.outcome == "passed" and result.rounds_used == 1
    assert result.open_violations == []
    assert checker.calls == []  # nothing to hint about
    assert scheduler.calls[0]["violations"] == []  # round 1 gets no violations


def test_a_failing_draft_is_fixed_in_round_two(inputs, reference):
    scheduler, checker = ScriptedScheduler([without(reference, 2), reference]), HintingRulesChecker()
    result = run_phase1(scheduler, checker, inputs)
    assert result.outcome == "passed" and result.rounds_used == 2
    assert result.final_draft.version == 2
    second = scheduler.calls[1]
    assert second["version"] == 2
    assert second["previous_draft"].version == 1
    assert len(second["violations"]) > 0
    assert all(v.fix_hint for v in second["violations"])  # the hints reached the Scheduler


def test_a_draft_that_never_passes_stops_after_three_rounds(inputs, reference):
    scheduler = ScriptedScheduler([without(reference, 3), without(reference, 3), without(reference, 3)])
    result = run_phase1(scheduler, HintingRulesChecker(), inputs)
    assert result.outcome == "stopped_after_3_rounds" and result.rounds_used == 3
    assert len(scheduler.calls) == 3  # never a fourth call
    assert result.open_violations, "the open problems must be listed"
    assert result.final_draft is not None


def test_the_best_draft_is_handed_to_the_manager(inputs, reference):
    # Each emptied shift is 2 hard violations (coverage and certification).
    # round 1: 3 shifts emptied (6), round 2: 1 shift (2, the best), round 3: 2 shifts (4)
    mon, tue, wed = ("2026-11-02", "day"), ("2026-11-03", "day"), ("2026-11-04", "day")
    scheduler = ScriptedScheduler([
        without_shifts(reference, [mon, tue, wed]),
        without_shifts(reference, [mon]),
        without_shifts(reference, [mon, tue]),
    ])
    result = run_phase1(scheduler, HintingRulesChecker(), inputs)
    assert [r.hard_violations for r in result.rounds] == [6, 2, 4]
    assert result.outcome == "stopped_after_3_rounds"
    assert result.final_draft.version == 2
    assert len(result.open_violations) == 2


def test_only_hard_violations_go_back_to_the_scheduler(inputs, reference):
    scheduler = ScriptedScheduler([without(reference, 2), reference])
    run_phase1(scheduler, HintingRulesChecker(), inputs)
    assert all(v.severity == "hard" for v in scheduler.calls[1]["violations"])


# --- a missing, broken or mislabeled draft is a failure, never a pass --------------


def test_no_draft_in_any_round_is_not_a_pass(inputs):
    result = run_phase1(ScriptedScheduler([None]), HintingRulesChecker(), inputs)
    assert result.outcome == "stopped_after_3_rounds"
    assert result.final_draft is None and result.rounds_used == 3
    assert all("no draft" in r.error for r in result.rounds)
    assert "nothing to approve" in format_report(result)


def test_an_unparseable_draft_fails_the_round_and_the_next_round_can_pass(inputs, reference):
    scheduler = ScriptedScheduler([{"case_id": "case-1", "assignments": "not a list"}, reference])
    result = run_phase1(scheduler, HintingRulesChecker(), inputs)
    assert result.outcome == "passed" and result.rounds_used == 2
    assert "could not be parsed" in result.rounds[0].error


def test_a_draft_labeled_with_the_wrong_version_is_rejected(inputs, reference):
    stale = reference.model_copy(update={"version": 1})  # round 2 gets a draft that says version 1
    scheduler = ScriptedScheduler([without(reference, 2), stale], stamp=False)
    scheduler.drafts[0] = without(reference, 2)  # version 1 already
    result = run_phase1(scheduler, HintingRulesChecker(), inputs)
    assert result.outcome == "stopped_after_3_rounds"
    assert "expected case-1, phase1-snapshot, version 2" in result.rounds[1].error


def test_a_draft_for_another_case_is_rejected(inputs, reference):
    other = reference.model_copy(update={"case_id": "case-99"})
    result = run_phase1(ScriptedScheduler([other], stamp=False), HintingRulesChecker(), inputs)
    assert result.final_draft is None and "case-99" in result.rounds[0].error


def test_a_crashing_scheduler_is_a_failed_round_not_a_crash(inputs):
    class Boom:
        def build(self, *a, **k):
            raise RuntimeError("model unavailable")

    result = run_phase1(Boom(), HintingRulesChecker(), inputs)
    assert result.final_draft is None and "model unavailable" in result.rounds[0].error


# --- the code's list always wins over the agent's ----------------------------------


def test_a_checker_that_hides_a_violation_is_overruled(inputs, reference):
    scheduler = ScriptedScheduler([without(reference, 3), reference])
    result = run_phase1(scheduler, DroppingRulesChecker(), inputs)
    sent_back = scheduler.calls[1]["violations"]
    assert len(sent_back) >= 2  # the full code list, including the one the agent hid
    assert result.rounds[0].agent_list_matched is False
    assert "differed" in result.rounds[0].note


def test_a_checker_that_invents_a_violation_is_overruled(inputs, reference):
    scheduler = ScriptedScheduler([without(reference, 2), reference])
    run_phase1(scheduler, InventingRulesChecker(), inputs)
    sent_back = scheduler.calls[1]["violations"]
    assert not any(v.date == "2026-11-08" and v.shift == "night" and v.found == "0 nurses" for v in sent_back)


def test_a_checker_that_agrees_is_marked_as_matching(inputs, reference):
    scheduler = ScriptedScheduler([without(reference, 2), reference])
    result = run_phase1(scheduler, HintingRulesChecker(), inputs)
    assert result.rounds[0].agent_list_matched is True and result.rounds[0].note == ""


def test_a_crashing_checker_still_lets_the_loop_continue(inputs, reference):
    scheduler = ScriptedScheduler([without(reference, 2), reference])
    result = run_phase1(scheduler, CrashingRulesChecker(), inputs)
    assert result.outcome == "passed" and result.rounds_used == 2
    assert result.rounds[0].agent_list_matched is False
    assert len(scheduler.calls[1]["violations"]) > 0  # the code's list, without hints
    assert all(v.fix_hint == "" for v in scheduler.calls[1]["violations"])


# --- the Scheduler's explanations never decide the outcome -------------------------


def test_notes_and_unfixable_rows_are_reported_but_never_make_a_pass(inputs, reference):
    from app.contract.models import NeedsManualReview, Unfixable

    bad = without(reference, 3).model_copy(update={
        "notes": ["Everything is fine, please approve."],
        "unfixable": [Unfixable(rule="coverage", date="2026-11-02", shift="day", reason="Nobody is free.")],
        "needs_manual_review": [NeedsManualReview(item_type="nurse", id="N012", note="No availability data.")],
    })
    result = run_phase1(ScriptedScheduler([bad, bad, bad]), HintingRulesChecker(), inputs)
    assert result.outcome == "stopped_after_3_rounds"
    assert len(result.unfixable) == 1 and len(result.needs_manual_review) == 1
    report = format_report(result)
    assert "did NOT pass" in report and "Nobody is free." in report and "N012" in report


# --- input files and the report ----------------------------------------------------


def test_inputs_load_from_the_mock_folder(inputs):
    assert len(inputs.roster) == 24 and len(inputs.demand) == 14 and len(inputs.availability) == 336


def test_report_lists_the_open_violations(inputs, reference):
    result = run_phase1(ScriptedScheduler([without(reference, 3)] * 3), HintingRulesChecker(), inputs)
    report = format_report(result)
    assert "Outcome: stopped_after_3_rounds after 3 round(s)" in report
    assert "- coverage:" in report and "- certification:" in report
    assert "Round 1: 2 hard violation(s)" in report


def test_demo_runs_from_the_command_line(capsys):
    assert main(["--demo", "clean"]) == 0
    assert "Outcome: passed after 1 round(s)" in capsys.readouterr().out
    assert main(["--demo", "fixes"]) == 0
    assert main(["--demo", "stuck"]) == 1
