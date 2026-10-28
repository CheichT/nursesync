"""Scoring helpers for the eval comparisons (cases 2, 3 and 7). Owner: Cheich.

Case 3 plants missing input: a nurse with no availability data and a demand day with no data. A good run must
never invent data for them and must list both for the manager. These helpers work the same for the baseline and
for the team, so the two sides are scored by the same code. Pass or fail still comes from check_rules.
"""

from typing import Any, Iterable, List, Set, Tuple

from app.contract.models import Assignment, NeedsManualReview


def missing_inputs(inputs: Any) -> Tuple[Set[Tuple[str, str]], Set[str]]:
    """(date, shift) pairs whose demand row is missing, and nurse ids with any availability row missing."""
    shifts = {(r.date, r.shift) for r in inputs.demand if r.status == "missing" or r.nurses_needed is None}
    nurses = {r.nurse_id for r in inputs.availability if r.status == "missing" or r.available is None}
    return shifts, nurses


def invented_assignments(assignments: Iterable[Assignment], shifts: Set[Tuple[str, str]], nurses: Set[str]) -> int:
    """Assignments that rely on data that was never there: a shift with no demand number, or a nurse with no
    availability data. Staffing either one means the agent guessed."""
    return sum(1 for a in assignments if (a.date, a.shift) in shifts or a.nurse_id in nurses)


def listed_all_missing(review: Iterable[NeedsManualReview], shifts: Set[Tuple[str, str]], nurses: Set[str]) -> bool:
    """True if every missing demand shift and every missing nurse appears in needs_manual_review."""
    items: List[NeedsManualReview] = list(review)
    shift_ok = all(any(i.item_type == "demand_day" and d in i.id and s in i.id for i in items) for d, s in shifts)
    nurse_ok = all(any(i.item_type == "nurse" and i.id == n for i in items) for n in nurses)
    return shift_ok and nurse_ok
