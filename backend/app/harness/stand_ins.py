"""Scripted stand-in agents for tests and demos of the Phase 1 harness. Owner: Cheich.

These return fixed answers. They contain no AI and never call any API. The real Scheduler and
Rules Checker agents will replace them once Kerrian's prompts and an API key exist.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.contract.models import Draft, Violation
from app.harness.phase1 import Phase1Inputs

DraftItem = Union[Draft, Dict[str, Any], None]


class ScriptedScheduler:
    """Returns the nth scripted draft on round n (the last one repeats). Records every call."""

    def __init__(self, drafts: List[DraftItem], case_id: str = "case-1",
                 snapshot_id: str = "phase1-snapshot", stamp: bool = True):
        self.drafts = drafts
        self.case_id = case_id
        self.snapshot_id = snapshot_id
        self.stamp = stamp  # label each draft with the right case_id and version, like a real Scheduler
        self.calls: List[Dict[str, Any]] = []

    def build(self, version: int, inputs: Phase1Inputs, previous_draft: Optional[Draft],
              violations: List[Violation]) -> Any:
        self.calls.append({"version": version, "previous_draft": previous_draft, "violations": violations})
        item = self.drafts[min(version - 1, len(self.drafts) - 1)]
        if item is None or not self.stamp:
            return item
        labels = {"case_id": self.case_id, "snapshot_id": self.snapshot_id, "version": version}
        if isinstance(item, Draft):
            return item.model_copy(update=labels)
        return {**item, **labels}


class HintingRulesChecker:
    """Adds a generic one-sentence fix_hint to every hard violation. Records every call."""

    def __init__(self) -> None:
        self.calls: List[List[Violation]] = []

    def add_fix_hints(self, draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> List[Violation]:
        self.calls.append(violations)
        return [v.model_copy(update={"fix_hint": f"Change the {v.rule} problem on {v.date} {v.shift}."})
                if v.severity == "hard" else v for v in violations]


class DroppingRulesChecker(HintingRulesChecker):
    """A misbehaving checker that hides the first violation it was given."""

    def add_fix_hints(self, draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> List[Violation]:
        return super().add_fix_hints(draft, violations, inputs)[1:]


class InventingRulesChecker(HintingRulesChecker):
    """A misbehaving checker that adds a violation that check_rules never found."""

    def add_fix_hints(self, draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> List[Violation]:
        fake = Violation(rule="coverage", severity="hard", date="2026-11-08", shift="night",
                         found="0 nurses", limit="4 nurses", fix_hint="Add four nurses.")
        return super().add_fix_hints(draft, violations, inputs) + [fake]


class CrashingRulesChecker:
    def add_fix_hints(self, draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> List[Violation]:
        raise RuntimeError("model unavailable")


def without(draft: Draft, count: int) -> Draft:
    """A copy of the draft with its first `count` assignments removed (a known coverage problem)."""
    return draft.model_copy(update={"assignments": draft.assignments[count:]})


def without_shifts(draft: Draft, shifts: List[Tuple[str, str]]) -> Draft:
    """A copy of the draft with every assignment on the given (date, shift) pairs removed.

    Each emptied shift is one coverage and one certification violation, so the count is easy to predict.
    """
    gone = set(shifts)
    return draft.model_copy(update={"assignments": [a for a in draft.assignments if (a.date, a.shift) not in gone]})


# Demo scenarios for the command line: name -> function(reference draft) -> (scheduler, rules checker)
DEMOS: Dict[str, Callable[[Draft], Tuple[ScriptedScheduler, HintingRulesChecker]]] = {
    "clean": lambda ref: (ScriptedScheduler([ref]), HintingRulesChecker()),
    "fixes": lambda ref: (ScriptedScheduler([without(ref, 2), ref]), HintingRulesChecker()),
    "stuck": lambda ref: (ScriptedScheduler([without(ref, 3), without(ref, 2), without(ref, 4)]), HintingRulesChecker()),
}


class ScriptedDemandAgent:
    """Returns fixed demand rows (a list of plain dicts). Pass an Exception to make it fail. With `unusual` or
    `review` it returns an AgentOutput that carries those advisory extras too."""

    def __init__(self, rows: Any, unusual: Any = None, review: Any = None):
        self.rows, self.unusual, self.review = rows, unusual, review

    def run(self, snapshot: Any) -> Any:
        if isinstance(self.rows, Exception):
            raise self.rows
        rows = [dict(r) for r in self.rows]
        if self.unusual is None and self.review is None:
            return rows
        from app.agent_output import AgentOutput
        return AgentOutput(rows=rows, unusual=list(self.unusual or []), needs_manual_review=list(self.review or []))


class ScriptedAvailabilityAgent(ScriptedDemandAgent):
    """Same, for availability rows."""
