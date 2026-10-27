"""check_rules: plain code that decides whether a draft schedule follows the hard rules.

Owner: Cheich. Source of truth: the PRD, sections 3b (check_rules, violation format) and 3e.

No AI is involved. It reads only the draft's `assignments` and the input files (roster,
demand, availability, rules). It never reads the draft's notes, reasoning or unfixable rows,
so the answer is the same however the Scheduler explained its choices.

Hard rules (any one fails the draft): rest time, weekly hours, consecutive shifts,
certification, availability, coverage. Fairness is soft: it is reported but never fails a draft.

Assumptions to confirm (the PRD is silent or ambiguous on these):
  * A shift with MORE nurses than the demand row asks for is not a violation. Only fewer is.
  * "Shifts in a row" means consecutive calendar days with a shift.
  * No availability data for a nurse and shift counts as a hard availability violation.
  * If availability rows for the same nurse, date and shift disagree, the least permissive wins.
  * hours_this_week from the roster is added to the week of the earliest shift in the draft.
  * "Night and weekend shifts" are shifts that are a night shift or start on a Saturday or Sunday.
    The fairness result names the nurse with the most such shifts, and their first such shift.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from app.contract.models import (
    Assignment,
    AvailabilityRow,
    CheckRulesResult,
    DemandRow,
    Draft,
    Nurse,
    RulesConfig,
    SoftTradeoff,
    Violation,
)

_SHIFT_ORDER = {"day": 0, "night": 1}
_RULE_ORDER = {"coverage": 0, "availability": 1}  # fixed first; the rest sort after, by date and shift
_REASON_TEXT = {"approved_time_off": "approved time off", "call_out": "a call-out", "none": "marked unavailable"}


class DraftRejected(ValueError):
    """The draft could not be parsed. The caller must treat this as a failure, never as a pass."""


def _span(a: Assignment) -> Tuple[datetime, datetime]:
    start = datetime.fromisoformat(f"{a.date}T{a.shift_start}")
    end = datetime.fromisoformat(f"{a.date}T{a.shift_end}")
    if end <= start:  # a night shift ends the next morning
        end += timedelta(days=1)
    return start, end


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def _nurses(n: int) -> str:
    return f"{n} nurse" if n == 1 else f"{n} nurses"


def _week_start(day: datetime) -> str:
    return (day - timedelta(days=day.weekday())).date().isoformat()


def check_rules(
    draft: Draft,
    demand: List[DemandRow],
    availability: List[AvailabilityRow],
    roster: List[Nurse],
    rules: RulesConfig,
) -> CheckRulesResult:
    """Check a draft against the hard rules. Returns the result, echoing case_id and version.

    The draft is validated again first, so one that was edited after it was built (and so skipped
    validation) cannot reach the rules. An invalid draft raises DraftRejected.
    """
    try:
        draft = Draft.model_validate(draft.model_dump())
    except ValidationError as err:
        raise DraftRejected(f"draft could not be parsed: {str(err).splitlines()[0]}") from err
    assignments = draft.assignments
    violations: List[Violation] = []

    by_nurse: Dict[str, List[Assignment]] = defaultdict(list)
    for a in assignments:
        by_nurse[a.nurse_id].append(a)
    for rows in by_nurse.values():
        rows.sort(key=lambda a: (_span(a)[0], _SHIFT_ORDER[a.shift]))

    # --- rest time ---------------------------------------------------------------
    for nid, rows in by_nurse.items():
        for prev, cur in zip(rows, rows[1:]):
            gap = (_span(cur)[0] - _span(prev)[1]).total_seconds() / 3600
            if gap < rules.min_rest_hours:
                found = "overlapping shifts" if gap < 0 else f"{_num(gap)} hours of rest"
                violations.append(Violation(
                    rule="rest_time", severity="hard", nurse_id=nid, date=cur.date, shift=cur.shift,
                    found=found, limit=f"{rules.min_rest_hours} hours of rest",
                ))

    # --- weekly hours ------------------------------------------------------------
    carry = {n.nurse_id: n.hours_this_week for n in roster}
    first_week = _week_start(min((_span(a)[0] for a in assignments), default=datetime.min)) if assignments else ""
    for nid, rows in by_nurse.items():
        totals: Dict[str, float] = defaultdict(float)
        crossed: Dict[str, Assignment] = {}
        for a in rows:
            start, end = _span(a)
            week = _week_start(start)
            if week not in totals and week == first_week:
                totals[week] = carry.get(nid, 0)
            totals[week] += (end - start).total_seconds() / 3600
            if totals[week] > rules.max_weekly_hours and week not in crossed:
                crossed[week] = a
        for week, a in crossed.items():
            violations.append(Violation(
                rule="weekly_hours", severity="hard", nurse_id=nid, date=a.date, shift=a.shift,
                found=f"{_num(totals[week])} hours this week", limit=f"{rules.max_weekly_hours} hours max",
            ))

    # --- consecutive shifts ------------------------------------------------------
    for nid, rows in by_nurse.items():
        first_on_day: Dict[str, Assignment] = {}
        for a in rows:
            first_on_day.setdefault(a.date, a)
        runs: List[List[str]] = []
        for d in sorted(first_on_day):
            if runs and (datetime.fromisoformat(d) - datetime.fromisoformat(runs[-1][-1])).days == 1:
                runs[-1].append(d)
            else:
                runs.append([d])
        for run in runs:
            if len(run) > rules.max_consecutive_shifts:  # one violation per run, at the first extra day
                over = first_on_day[run[rules.max_consecutive_shifts]]
                violations.append(Violation(
                    rule="consecutive_shifts", severity="hard", nurse_id=nid, date=over.date, shift=over.shift,
                    found=f"{len(run)} shifts in a row", limit=f"{rules.max_consecutive_shifts} shifts max",
                ))

    # --- certification and coverage (one pass over the demand rows) --------------
    cert_of = {n.nurse_id: set(n.certifications) for n in roster}
    on_shift: Dict[Tuple[str, str, str], List[str]] = defaultdict(list)
    for a in assignments:
        on_shift[(a.unit, a.date, a.shift)].append(a.nurse_id)
    for row in demand:
        if row.nurses_needed is None:  # missing demand is an open gap for the Scheduler, not a coverage check
            continue
        crew = on_shift.get((row.unit, row.date, row.shift), [])
        for cert in rules.required_certifications_per_shift:
            have = sum(1 for n in crew if cert in cert_of.get(n, set()))
            if have < 1:
                violations.append(Violation(
                    rule="certification", severity="hard", date=row.date, shift=row.shift,
                    found=f"{_nurses(have)} with {cert}", limit=f"1 nurse with {cert}",
                ))
        if len(crew) < row.nurses_needed:
            violations.append(Violation(
                rule="coverage", severity="hard", date=row.date, shift=row.shift,
                found=_nurses(len(crew)), limit=_nurses(row.nurses_needed),
            ))

    # --- availability ------------------------------------------------------------
    avail = _most_cautious_rows(availability)
    for a in assignments:
        r = avail.get((a.nurse_id, a.date, a.shift))
        if r is None or r.status == "missing" or r.available is None:
            found = "no availability data"
        elif r.available is False:
            found = f"unavailable ({_REASON_TEXT.get(r.reason or 'none', 'marked unavailable')})"
        else:
            continue
        violations.append(Violation(
            rule="availability", severity="hard", nurse_id=a.nurse_id, date=a.date, shift=a.shift,
            found=found, limit="available",
        ))

    violations.sort(key=lambda v: (_RULE_ORDER.get(v.rule, 2), v.date, _SHIFT_ORDER[v.shift], v.nurse_id, v.rule))

    return CheckRulesResult(
        case_id=draft.case_id,
        version=draft.version,
        passed=not violations,
        violations=violations,
        soft_tradeoffs=_fairness(assignments, roster, rules),
    )


def _permission(row: AvailabilityRow) -> int:
    """0 = unavailable, 1 = no usable data, 2 = available. Lower is more cautious."""
    if row.status == "missing" or row.available is None:
        return 1
    return 2 if row.available else 0


def _most_cautious_rows(rows: List[AvailabilityRow]) -> Dict[Tuple[str, str, str], AvailabilityRow]:
    """One row per (nurse, date, shift). If rows disagree, the least permissive wins, in any order.

    A later "available" row can therefore never cancel approved time off.
    """
    chosen: Dict[Tuple[str, str, str], AvailabilityRow] = {}
    for r in rows:
        key = (r.nurse_id, r.date, r.shift)
        if key not in chosen or _permission(r) < _permission(chosen[key]):
            chosen[key] = r
    return chosen


def _fairness(assignments: List[Assignment], roster: List[Nurse], rules: RulesConfig) -> List[SoftTradeoff]:
    """Soft: the gap between the most and fewest night and weekend shifts. Never fails a draft."""
    if not roster:
        return []
    mine: Dict[str, List[Assignment]] = {n.nurse_id: [] for n in roster}
    for a in assignments:
        weekend = datetime.fromisoformat(a.date).weekday() >= 5
        if (a.shift == "night" or weekend) and a.nurse_id in mine:
            mine[a.nurse_id].append(a)
    counts = {nid: len(rows) for nid, rows in mine.items()}
    top = max(counts.values())
    bottom = min(counts.values())
    gap = top - bottom
    if gap <= rules.max_fairness_gap:
        return []
    top_id = sorted(nid for nid, c in counts.items() if c == top)[0]
    first = sorted(mine[top_id], key=lambda a: (a.date, _SHIFT_ORDER[a.shift]))[0]
    note = (f"{top_id} has {top} night and weekend shifts and the fewest nurse has {bottom}; "
            f"the gap is {gap}, above the limit of {rules.max_fairness_gap}.")
    return [SoftTradeoff(rule="fairness", nurse_id=top_id, date=first.date, shift=first.shift, note=note)]


def check_rules_from_dicts(
    raw_draft: Dict[str, Any],
    demand: List[DemandRow],
    availability: List[AvailabilityRow],
    roster: List[Nurse],
    rules: RulesConfig,
) -> CheckRulesResult:
    """Parse a raw draft, then check it. A draft that does not parse raises DraftRejected."""
    try:
        draft = Draft(**raw_draft)
    except (ValidationError, TypeError) as err:
        raise DraftRejected(f"draft could not be parsed: {err}") from err
    return check_rules(draft, demand, availability, roster, rules)
