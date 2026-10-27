"""Run a Phase 1 eval card. Cases 1, 4, 5, 6, 7 call the live agents (a few cents per run); 13 and 14 are code-only.

Usage: cd backend && ../.venv/bin/python -m app.run_eval case_04 [--runs 3]
Cases: case_01 case_04 case_05 case_06 case_07 case_13 case_14. See backend/evals/phase1/ for what each should show.
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
from app.contract.models import Draft
from app.harness.phase1 import DEFAULT_DATA, Phase1Result, format_report, load_inputs, load_scenario, run_phase1
from app.harness.rules import check_rules
from app.harness.stand_ins import DroppingRulesChecker, HintingRulesChecker, ScriptedScheduler, without

LIVE_CASES = {"case_01": ("mock", False), "case_04": ("case_04", True), "case_05": ("case_05", False),
              "case_06": ("case_06", True), "case_07": ("mock", False)}


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


def summarize(result: Phase1Result) -> Dict[str, Any]:
    hard = [v for v in result.open_violations if v.severity == "hard"]
    return {"outcome": result.outcome, "rounds_used": result.rounds_used, "hard_violations": len(hard),
            "unfixable_rows": len(result.unfixable), "violations": [f"{v.rule} {v.nurse_id or '-'} {v.date} {v.shift}" for v in hard],
            "round_errors": [r.error for r in result.rounds if r.error]}


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
    parser.add_argument("case", choices=sorted(list(LIVE_CASES) + ["case_13", "case_14"]))
    parser.add_argument("--runs", type=int, default=1, help="how many times to run it (the cards ask for 3)")
    args = parser.parse_args(argv)

    if args.case in ("case_13", "case_14"):
        report = case_13() if args.case == "case_13" else case_14()
        print(json.dumps(report, indent=2))
        return 0 if report["pass"] else 1

    scenario, planted = LIVE_CASES[args.case]
    for run in range(1, args.runs + 1):
        print(f"--- {args.case} run {run} of {args.runs} ---")
        if args.case == "case_07":
            inputs = load_inputs()
            print("baseline:", json.dumps(run_baseline(inputs)))
        result = run_team(scenario, planted)
        print("team:    ", json.dumps(summarize(result)))
        if args.runs == 1:
            print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
