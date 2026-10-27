"""The Phase 1 test harness: runs the Scheduler and Rules Checker loop on one unit and one week.

Owner: Cheich. Source of truth: the PRD, "Phase 1 test harness".

There is no orchestrator in phase 1. This small script:
  1. reads the input files (demand, availability, roster, rules) from disk,
  2. asks the Scheduler for a draft,
  3. runs check_rules IN CODE on the draft,
  4. if there are hard violations, asks the Rules Checker agent to add a fix_hint to each, then
     compares the agent's list to the code's list (same rule, nurse_id, date and shift) and
     uses the code's list if they differ,
  5. sends the violations back to the Scheduler, for up to 3 rounds,
  6. prints the final draft, open violations, unfixable rows and needs_manual_review rows.

Pass or fail always comes from check_rules, never from an agent. A draft that is missing,
unparseable, or labeled with the wrong case_id or version counts as a failed round, never a pass.

Agents only ever receive copies of the inputs, the draft and the violations, so an agent that edits
what it was given cannot change the official data or a draft that was already checked.

The agents are plug-in pieces (see `Scheduler` and `RulesChecker`). Scripted stand-ins live in
stand_ins.py for tests and demos. The real AI-backed agents come later, once the prompts exist.
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple

from collections import Counter

from pydantic import BaseModel, ValidationError, model_validator

from app.contract.models import (
    AvailabilityRow,
    DemandRow,
    Draft,
    NeedsManualReview,
    Nurse,
    RulesConfig,
    SoftTradeoff,
    Unfixable,
    Violation,
)
from app.harness.rules import DraftRejected, check_rules

MAX_ROUNDS = 3
DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "mock"


class Phase1Inputs(BaseModel):
    """The four input files, parsed. A file with duplicate rows is rejected, never quietly merged."""

    demand: List[DemandRow]
    availability: List[AvailabilityRow]
    roster: List[Nurse]
    rules: RulesConfig

    @model_validator(mode="after")
    def _no_duplicate_rows(self):
        ids = Counter(n.nurse_id for n in self.roster)
        repeated = sorted(i for i, c in ids.items() if c > 1)
        if repeated:
            raise ValueError(f"roster has duplicate nurse_id values: {repeated}")
        keys = Counter((r.nurse_id, r.date, r.shift) for r in self.availability)
        repeated_rows = sorted(k for k, c in keys.items() if c > 1)
        if repeated_rows:
            shown = ", ".join(f"{n} {d} {sh}" for n, d, sh in repeated_rows[:5])
            more = f" (and {len(repeated_rows) - 5} more)" if len(repeated_rows) > 5 else ""
            raise ValueError(f"availability has more than one row for the same nurse, date and shift: {shown}{more}")
        return self


def load_inputs(data_dir: Path = DEFAULT_DATA) -> Phase1Inputs:
    data_dir = Path(data_dir)

    def read(name: str) -> Any:
        return json.loads((data_dir / name).read_text())

    return Phase1Inputs(
        demand=[DemandRow(**r) for r in read("demand.json")],
        availability=[AvailabilityRow(**r) for r in read("availability.json")],
        roster=[Nurse(**r) for r in read("roster.json")],
        rules=RulesConfig(**read("rules.json")),
    )


class Scheduler(Protocol):
    def build(self, version: int, inputs: Phase1Inputs, previous_draft: Optional[Draft],
              violations: List[Violation]) -> Any:
        """Return a draft (a Draft or a plain dict). `violations` is empty on round 1."""


class RulesChecker(Protocol):
    def add_fix_hints(self, draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> List[Violation]:
        """Return the violations with a one-sentence fix_hint on each hard one."""


class RoundLog(BaseModel):
    version: int
    error: str = ""  # why the round produced no checked draft, if it did not
    hard_violations: int = 0
    agent_list_matched: Optional[bool] = None  # did the Rules Checker's list match the code's list?
    note: str = ""


class Phase1Result(BaseModel):
    case_id: str
    snapshot_id: str
    outcome: Literal["passed", "stopped_after_3_rounds"]
    rounds_used: int
    final_draft: Optional[Draft] = None
    open_violations: List[Violation]
    soft_tradeoffs: List[SoftTradeoff]
    unfixable: List[Unfixable]
    needs_manual_review: List[NeedsManualReview]
    rounds: List[RoundLog]


def _key(v: Violation) -> Tuple[str, str, str, str]:
    return (v.rule, v.nurse_id, v.date, v.shift)


def _get_draft(scheduler: Scheduler, version: int, inputs: Phase1Inputs, previous: Optional[Draft],
               violations: List[Violation], case_id: str, snapshot_id: str, log: RoundLog) -> Optional[Draft]:
    try:
        # The agent gets COPIES of everything, so nothing it does can change the official data
        # or the drafts the harness is keeping and checking.
        raw = scheduler.build(
            version,
            inputs.model_copy(deep=True),
            previous.model_copy(deep=True) if previous is not None else None,
            [v.model_copy(deep=True) for v in violations],
        )
    except Exception as err:  # an agent failing is a failed round, not a crash
        log.error = f"the Scheduler failed: {err}"
        return None
    if raw is None:
        log.error = "the Scheduler returned no draft"
        return None
    try:
        # always re-validate, even a Draft object: it may have been edited after it was built
        draft = Draft.model_validate(raw.model_dump() if isinstance(raw, Draft) else raw)
    except (ValidationError, TypeError) as err:
        log.error = f"draft could not be parsed: {str(err).splitlines()[0]}"
        return None
    if (draft.case_id, draft.snapshot_id, draft.version) != (case_id, snapshot_id, version):
        log.error = (f"draft is labeled {draft.case_id}, {draft.snapshot_id}, version {draft.version}; "
                     f"expected {case_id}, {snapshot_id}, version {version}")
        return None
    return draft


def _fix_hints(rules_checker: RulesChecker, draft: Draft, code_list: List[Violation],
               inputs: Phase1Inputs, log: RoundLog) -> List[Violation]:
    """Ask the agent for hints, then keep the CODE's list. The agent's hints are copied onto matching rows."""
    try:
        agent_list = rules_checker.add_fix_hints(
            draft.model_copy(deep=True),
            [v.model_copy(deep=True) for v in code_list],
            inputs.model_copy(deep=True),
        )
    except Exception as err:
        log.agent_list_matched = False
        log.note = f"the Rules Checker failed ({err}); using the code's list without hints"
        return list(code_list)
    agent_by_key = {_key(v): v for v in agent_list if v.severity == "hard"}
    log.agent_list_matched = {_key(v) for v in code_list} == set(agent_by_key)
    if not log.agent_list_matched:
        log.note = "the Rules Checker's list differed from the code's list; the code's list was used"
    merged = []
    for v in code_list:
        hint = agent_by_key[_key(v)].fix_hint if _key(v) in agent_by_key else ""
        merged.append(v.model_copy(update={"fix_hint": hint}) if hint else v)
    return merged


def run_phase1(scheduler: Scheduler, rules_checker: RulesChecker, inputs: Phase1Inputs,
               case_id: str = "case-1", snapshot_id: str = "phase1-snapshot",
               max_rounds: int = MAX_ROUNDS) -> Phase1Result:
    logs: List[RoundLog] = []
    previous: Optional[Draft] = None
    hints: List[Violation] = []
    best: Optional[Tuple[int, Draft, Any]] = None  # (hard violation count, draft, check result)

    for version in range(1, max_rounds + 1):
        log = RoundLog(version=version)
        logs.append(log)
        draft = _get_draft(scheduler, version, inputs, previous, hints, case_id, snapshot_id, log)
        if draft is None:
            continue  # a failed round; the next round gets the same hints
        try:
            result = check_rules(draft, inputs.demand, inputs.availability, inputs.roster, inputs.rules)
        except DraftRejected as err:  # for example shift times that differ from rules.shift_times
            log.error = str(err)
            continue  # a failed round; the draft is not kept
        previous = draft
        log.hard_violations = len(result.violations)
        if best is None or len(result.violations) <= best[0]:
            best = (len(result.violations), draft, result)
        if result.passed:
            return _finish("passed", case_id, snapshot_id, logs, best)
        if version < max_rounds:
            hints = _fix_hints(rules_checker, draft, result.violations, inputs, log)
    return _finish("stopped_after_3_rounds", case_id, snapshot_id, logs, best)


def _finish(outcome: str, case_id: str, snapshot_id: str, logs: List[RoundLog],
            best: Optional[Tuple[int, Draft, Any]]) -> Phase1Result:
    if best is None:  # no valid draft in any round
        return Phase1Result(case_id=case_id, snapshot_id=snapshot_id, outcome="stopped_after_3_rounds",
                            rounds_used=len(logs), open_violations=[], soft_tradeoffs=[], unfixable=[],
                            needs_manual_review=[], rounds=logs)
    _, draft, result = best
    return Phase1Result(
        case_id=case_id, snapshot_id=snapshot_id, outcome=outcome, rounds_used=len(logs),
        final_draft=draft, open_violations=result.violations, soft_tradeoffs=result.soft_tradeoffs,
        unfixable=draft.unfixable, needs_manual_review=draft.needs_manual_review, rounds=logs,
    )


def _clean(value: Any, limit: int = 300) -> str:
    """Make any text safe to print as ONE line.

    Agents write free text, and a person reads this report. Line breaks, tabs and other whitespace
    become a single space, and control and invisible characters (terminal escapes, right-to-left
    overrides, null bytes) are removed. So agent text can never start a new line that looks like part
    of the report, such as a fake "Outcome: passed" line, or change how a terminal draws the page.
    Long text is cut at `limit` characters.
    """
    kept = []
    for ch in str(value):
        category = unicodedata.category(ch)
        if ch.isspace() or category in ("Zl", "Zp"):
            kept.append(" ")
        elif category in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue
        else:
            kept.append(ch)
    text = " ".join("".join(kept).split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def format_report(result: Phase1Result) -> str:
    """A plain-text report for the person running the harness. Every piece of text goes through _clean."""
    c = _clean
    lines = [f"Case {c(result.case_id)} ({c(result.snapshot_id)})",
             f"Outcome: {result.outcome} after {result.rounds_used} round(s)", ""]
    for r in result.rounds:
        status = f"error: {c(r.error)}" if r.error else f"{r.hard_violations} hard violation(s)"
        extra = f" | {c(r.note)}" if r.note else ""
        lines.append(f"  Round {r.version}: {status}{extra}")
    lines.append("")
    if result.final_draft is None:
        lines.append("No valid draft was produced, so there is nothing to approve.")
    else:
        a = result.final_draft.assignments
        lines.append(f"Final draft: version {result.final_draft.version}, {len(a)} assignment(s), "
                     f"{len(result.final_draft.open_gaps)} open gap(s)")
        if result.outcome != "passed":
            lines.append("This draft did NOT pass. Do not call it passing.")
    lines.append("")
    lines.append(f"Open hard violations ({len(result.open_violations)}):")
    for v in result.open_violations:
        who = c(v.nurse_id) or "(whole shift)"
        hint = f" Hint: {c(v.fix_hint)}" if v.fix_hint else ""
        lines.append(f"  - {v.rule}: {who}, {c(v.date)} {v.shift}. Found {c(v.found)}; limit {c(v.limit)}.{hint}")
    lines.append(f"Unfixable rows ({len(result.unfixable)}):")
    for u in result.unfixable:
        lines.append(f"  - {u.rule}: {c(u.nurse_id) or '(whole shift)'}, {c(u.date)} {u.shift}. {c(u.reason)}")
    lines.append(f"Needs manual review ({len(result.needs_manual_review)}):")
    for n in result.needs_manual_review:
        lines.append(f"  - {n.item_type} {c(n.id)}: {c(n.note)}")
    lines.append(f"Soft tradeoffs ({len(result.soft_tradeoffs)}):")
    for t in result.soft_tradeoffs:
        lines.append(f"  - {t.rule}: {c(t.nurse_id)}, {c(t.date)} {t.shift}. {c(t.note)}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """Run a demo with scripted stand-in agents. The real agents are not wired in yet."""
    from app.harness import stand_ins

    parser = argparse.ArgumentParser(description="Phase 1 test harness (demo with stand-in agents).")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="folder with the four input files")
    parser.add_argument("--demo", choices=sorted(stand_ins.DEMOS), default="fixes",
                        help="which scripted scenario to run")
    args = parser.parse_args(argv)

    inputs = load_inputs(Path(args.data))
    reference = Draft(**json.loads((Path(args.data) / "reference_draft.json").read_text()))
    scheduler, checker = stand_ins.DEMOS[args.demo](reference)
    result = run_phase1(scheduler, checker, inputs)
    print(format_report(result))
    return 0 if result.outcome == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
