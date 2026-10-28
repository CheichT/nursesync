"""Run an eval card. Cases 1, 2, 4, 5, 6, 7 and 10 call the live agents (cents to about a dollar per run); 3, 13 and
14 are code-only for the team (case 3 also runs the live baseline).

Usage: cd backend && ../.venv/bin/python -m app.run_eval case_04 [--runs 3]
Cases: case_01 case_02 case_03 case_04 case_05 case_06 case_07 case_10 case_13 case_14.
Case 10 (late call-out) builds a clean weekly case with scripted agents (free), then the live Scheduler handles the call-out.
Cases 2, 3 and 7 run the single-agent baseline and the team on the same inputs, so you can compare them.
See backend/evals/phase1/ for what each should show.
Pass or fail always comes from check_rules, never from an agent.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.agents.baseline.agent import run_baseline
from app.agents.rules_checker.agent import AnthropicRulesChecker
from app.agents.scheduler.agent import AnthropicScheduler
from app.contract.case_record import AvailabilityResult, DemandResult, Snapshot
from app.callouts import run_call_out
from app.contract.models import Callout, Draft
from app.harness.eval_scoring import listed_all_missing, missing_inputs
from app.harness.phase1 import DEFAULT_DATA, Phase1Result, format_report, load_inputs, load_scenario, run_phase1
from app.orchestrator import make_snapshot, run_case, schedule_case, snapshot_id_for, status_counts
from app.harness.rules import check_rules
from app.harness.stand_ins import (
    DroppingRulesChecker,
    HintingRulesChecker,
    ScriptedAvailabilityAgent,
    ScriptedDemandAgent,
    ScriptedScheduler,
    without,
)

LIVE_CASES = {"case_01": ("mock", False), "case_02": ("case_02", False), "case_03": ("case_03", False),
              "case_04": ("case_04", True), "case_05": ("case_05", False), "case_06": ("case_06", True),
              "case_07": ("mock", False)}
COMPARE_CASES = ("case_02", "case_03", "case_07")  # run the baseline and the team on the same inputs


class NeverScheduler:
    """The team must stop before the Scheduler when input is missing. If this is ever called, the run fails loudly."""

    def build(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the Scheduler ran although required input was missing")


class PlantedFirstScheduler:
    """Round 1 returns the planted draft (labeled for the run); later rounds go to the real Scheduler."""

    def __init__(self, planted: Dict[str, Any], live: Any, case_id: str = "case-1", snapshot_id: str = "phase1-snapshot"):
        self.planted, self.live, self.labels = planted, live, {"case_id": case_id, "snapshot_id": snapshot_id}

    def build(self, version, inputs, previous_draft, violations):
        if version == 1:
            return {**self.planted, **self.labels, "version": 1}
        return self.live.build(version, inputs, previous_draft, violations)


def run_team(name: str, planted: bool) -> Phase1Result:
    inputs, planted_draft = (load_inputs(), None) if name == "mock" else load_scenario(name)
    scheduler: Any = AnthropicScheduler()
    if planted and planted_draft:
        scheduler = PlantedFirstScheduler(planted_draft, scheduler)
    return run_phase1(scheduler, AnthropicRulesChecker(), inputs)


def summarize(result: Phase1Result, inputs: Any = None) -> Dict[str, Any]:
    """The team's numbers. With `inputs`, also the same coverage numbers the baseline reports, so the two sides
    can be compared: fully_staffed_shifts, shifts_in_week, coverage_rate."""
    hard = [v for v in result.open_violations if v.severity == "hard"]
    out: Dict[str, Any] = {
        "outcome": result.outcome, "rounds_used": result.rounds_used, "hard_violations": len(hard),
        "unfixable_rows": len(result.unfixable),
        "violations": [f"{v.rule} {v.nurse_id or '-'} {v.date} {v.shift}" for v in hard],
        "round_errors": [r.error for r in result.rounds if r.error]}
    if inputs is not None:
        crew: Dict[tuple, int] = {}
        for a in (result.final_draft.assignments if result.final_draft else []):
            crew[(a.unit, a.date, a.shift)] = crew.get((a.unit, a.date, a.shift), 0) + 1
        staffed = sum(1 for d in inputs.demand if crew.get((d.unit, d.date, d.shift), 0) == d.nurses_needed)
        out.update(fully_staffed_shifts=staffed, shifts_in_week=len(inputs.demand),
                   coverage_rate=round(staffed / len(inputs.demand), 3),
                   open_gaps_listed=len(result.final_draft.open_gaps) if result.final_draft else 0)
    return out


def run_team_missing(name: str) -> Dict[str, Any]:
    """Case 3 for the team: required input is missing, so the orchestrator must stop before the Scheduler runs.
    No agent is called, so this costs nothing. Scored by the same helpers as the baseline."""
    inputs, _ = load_scenario(name)
    snapshot: Snapshot = make_snapshot(inputs.roster, inputs.rules, inputs.demand[0].unit, inputs.demand[0].date,
                                       "snap-eval")
    record = schedule_case(NeverScheduler(), HintingRulesChecker(), snapshot,
                           DemandResult(rows=inputs.demand, counts=status_counts(inputs.demand)),
                           AvailabilityResult(rows=inputs.availability, counts=status_counts(inputs.availability)),
                           "eval-case")
    shifts, nurses = missing_inputs(inputs)
    return {"outcome": record.outcome, "drafts": len(record.drafts), "invented_assignments": 0,
            "listed_missing": listed_all_missing(record.needs_manual_review, shifts, nurses),
            "stop_reason": record.stop_reason}


def _raw(name: str) -> List[Dict[str, Any]]:
    rows = json.loads((DEFAULT_DATA / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def case_10(make_scheduler: Optional[Callable[[str, str], Any]] = None,
            rules_checker: Optional[Any] = None) -> Dict[str, Any]:
    """Eval case 10, late call-out. A clean weekly case is waiting for approval (built free, with scripted agents).
    N006 calls out of Wed 2026-11-04 day. The Scheduler (live unless told otherwise) must rebuild only that shift with
    the rest of the week locked. Pass: the old case is out_of_date, the new case passes check_rules for the whole week,
    N006 is not on the shift, and nothing locked was changed (code rejects a draft that does, and that shows up as a
    round error)."""
    inputs = load_inputs()
    ref = Draft(**json.loads((DEFAULT_DATA / "reference_draft.json").read_text()))
    parent = run_case(ScriptedDemandAgent(_raw("demand.json")), ScriptedAvailabilityAgent(_raw("availability.json")),
                      ScriptedScheduler([ref], case_id="eval-parent", snapshot_id=snapshot_id_for("eval-parent")),
                      HintingRulesChecker(), inputs.roster, inputs.rules, "7W", "2026-11-02", "eval-parent")
    built: List[Any] = []

    def live_scheduler(case_id: str, snapshot_id: str) -> Any:
        built.append(AnthropicScheduler(case_id=case_id, snapshot_id=snapshot_id))
        return built[-1]

    call = Callout(nurse_id="N006", date="2026-11-04", shift="day", reported_at="2026-11-03T22:15:00")
    old, child = run_call_out(parent, [call], "eval-call-out", make_scheduler or live_scheduler,
                              rules_checker or AnthropicRulesChecker(), inputs.roster, inputs.rules)
    on_shift = sorted(a.nurse_id for a in (child.final_draft.assignments if child.final_draft else [])
                      if (a.date, a.shift) == ("2026-11-04", "day"))
    before = sorted(a.nurse_id for a in ref.assignments if (a.date, a.shift) == ("2026-11-04", "day"))
    out_tokens = sum(c.get("output_tokens") or 0 for s in built for c in s.calls)
    report = {
        "old_status": old.status, "newer_case_id": old.newer_case_id, "child_trigger": child.trigger,
        "child_outcome": child.outcome, "rounds_used": child.rounds_used,
        "round_errors": [r.error for r in child.rounds if r.error],
        "locked_changes_rejected": sum("changed locked assignments" in r.error for r in child.rounds),
        "hard_violations": len(child.open_violations), "called_out_still_on_shift": "N006" in on_shift,
        "shift_before": before, "shift_after": on_shift, "kept": [n for n in on_shift if n in before],
        "suggestions": [f"{x.nurse_id}: {x.reason}" for x in (child.final_draft.suggestions if child.final_draft else [])],
        "scheduler_calls": sum(len(s.calls) for s in built), "scheduler_output_tokens": out_tokens,
    }
    report["pass"] = (old.status == "out_of_date" and child.status == "waiting_approval"
                      and child.outcome == "passed" and not report["called_out_still_on_shift"]
                      and child.final_draft is not None)
    return report


def case_13() -> Dict[str, Any]:
    """The Rules Checker hides a violation. The harness must keep the code's full list."""
    inputs = load_inputs()
    ref = Draft(**json.loads((DEFAULT_DATA / "reference_draft.json").read_text()))
    scheduler = ScriptedScheduler([without(ref, 3), ref])
    result = run_phase1(scheduler, DroppingRulesChecker(), inputs)
    code_count = result.rounds[0].hard_violations
    sent = len([v for v in scheduler.calls[1]["violations"] if v.severity == "hard"])
    ok = result.rounds[0].agent_list_matched is False and sent == code_count and code_count >= 2
    return {"pass": ok, "code_found": code_count, "sent_to_scheduler": sent,
            "mismatch_detected": result.rounds[0].agent_list_matched is False}


def case_14() -> Dict[str, Any]:
    """A missing, unparseable or stale check result must fail closed. Sub-cases A, B, C."""
    inputs = load_inputs()
    ref = Draft(**json.loads((DEFAULT_DATA / "reference_draft.json").read_text()))
    good = check_rules(ref, inputs.demand, inputs.availability, inputs.roster, inputs.rules)
    verdicts: Dict[str, Callable[..., Any]] = {
        "A_missing": lambda *a: None,
        "B_unparseable": lambda *a: {"garbage": True},
        "C_stale": lambda *a: good.model_copy(update={"version": 2}),
    }
    out: Dict[str, Any] = {}
    for name, checker in verdicts.items():
        result = run_phase1(ScriptedScheduler([ref]), HintingRulesChecker(), inputs, max_rounds=1, checker=checker)
        out[name] = {"outcome": result.outcome, "message": result.rounds[0].error, "pass": result.outcome != "passed"
                     and bool(result.rounds[0].error)}
    out["pass"] = all(v["pass"] for v in out.values())
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", choices=sorted(list(LIVE_CASES) + ["case_10", "case_13", "case_14"]))
    parser.add_argument("--runs", type=int, default=1, help="how many times to run it (the cards ask for 3)")
    args = parser.parse_args(argv)

    if args.case in ("case_13", "case_14"):
        report = case_13() if args.case == "case_13" else case_14()
        print(json.dumps(report, indent=2))
        return 0 if report["pass"] else 1

    if args.case == "case_10":
        reports = []
        for run in range(1, args.runs + 1):
            print(f"--- case_10 run {run} of {args.runs} ---")
            reports.append(case_10())
            print(json.dumps(reports[-1], indent=2))
        return 0 if all(r["pass"] for r in reports) else 1

    scenario, planted = LIVE_CASES[args.case]
    for run in range(1, args.runs + 1):
        print(f"--- {args.case} run {run} of {args.runs} ---")
        inputs = load_inputs() if scenario == "mock" else load_scenario(scenario)[0]
        if args.case in COMPARE_CASES:
            print("baseline:", json.dumps(run_baseline(inputs)))
        if any(missing_inputs(inputs)):  # required input is missing: the team must stop before the Scheduler
            print("team:    ", json.dumps(run_team_missing(scenario)))
            continue
        result = run_team(scenario, planted)
        print("team:    ", json.dumps(summarize(result, inputs)))
        if args.runs == 1:
            print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
