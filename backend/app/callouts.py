"""Late call-outs: a nurse calls out while a draft is still waiting for the manager. Owner: Cheich.

Source of truth: the PRD, "Late call-outs". The flow, all in code:
  1. only a case that is waiting_approval and has a draft can be updated; the manager can then never approve it,
  2. each call-out turns that nurse's availability row for that shift into unavailable (call_out),
  3. a NEW case starts (trigger call_out, parent_case_id, a new snapshot, the affected shifts listed),
  4. every assignment outside the affected shifts is locked: the Scheduler may not change it, and code rejects
     a draft that does (see phase1._call_out_problem),
  5. check_rules still checks the whole week, because a replacement's other shifts affect rest and hours,
  6. the old case becomes out_of_date.

The new run reuses the earlier case's demand and availability rows, so no agent is called again. Version one
only handles a case still waiting for approval (PRD eval 10). Nothing is sent to nurses.
"""

from datetime import datetime
from typing import Callable, List, Optional, Tuple

from app.case_store import CaseStore
from app.contract.case_record import AvailabilityResult, CaseRecord, DemandResult, ShiftRef
from app.contract.models import AvailabilityRow, Callout, Nurse, RulesConfig
from app.decisions import DecisionRefused, SchedulerFactory, _check_open, mark_out_of_date
from app.harness.phase1 import RulesChecker
from app.orchestrator import (
    building_record,
    make_snapshot,
    schedule_case,
    snapshot_id_for,
    status_counts,
    week_dates,
)

SHIFT_ORDER = {"day": 0, "night": 1}


def run_call_out(parent: CaseRecord, callouts: List[Callout], new_case_id: str, make_scheduler: SchedulerFactory,
                 rules_checker: RulesChecker, roster: List[Nurse], rules: RulesConfig,
                 now: Optional[Callable[[], datetime]] = None,
                 store: Optional[CaseStore] = None) -> Tuple[CaseRecord, CaseRecord]:
    """Returns (old_case, new_case). The old case is out_of_date. Raises DecisionRefused, with a message safe to
    show the manager, if the call-out cannot be applied. Nothing is saved when it raises."""
    _check_open(parent)
    if parent.final_draft is None:
        raise DecisionRefused("This case has no draft to update, so a call-out cannot be applied to it.")
    if not callouts:
        raise DecisionRefused("No call-outs were given.")

    on_roster = {n.nurse_id for n in roster}
    week = set(week_dates(parent.week_start))
    seen = set()
    unique: List[Callout] = []
    for c in callouts:
        if c.nurse_id not in on_roster:
            raise DecisionRefused(f"{c.nurse_id} is not on the roster, so the call-out cannot be applied.")
        if c.date not in week:
            raise DecisionRefused(f"{c.date} is outside the week this case covers.")
        if (c.nurse_id, c.date, c.shift) not in seen:
            seen.add((c.nurse_id, c.date, c.shift))
            unique.append(c)

    affected_keys = sorted({(c.date, c.shift) for c in unique}, key=lambda k: (k[0], SHIFT_ORDER[k[1]]))
    affected = [ShiftRef(date=d, shift=s) for d, s in affected_keys]
    affected_set = set(affected_keys)
    by_row = {(c.nurse_id, c.date, c.shift): c for c in unique}

    rows: List[AvailabilityRow] = []
    for row in parent.availability_result.rows:
        c = by_row.get((row.nurse_id, row.date, row.shift))
        if c is None:
            rows.append(row.model_copy(deep=True))
        else:
            rows.append(AvailabilityRow(nurse_id=row.nurse_id, date=row.date, shift=row.shift, available=False,
                                        reason="call_out", status="ok", note=f"call-out reported {c.reported_at}"))
    availability = AvailabilityResult(rows=rows, counts=status_counts(rows))
    demand = DemandResult(rows=[r.model_copy(deep=True) for r in parent.demand_result.rows],
                          counts=parent.demand_result.counts.model_copy())

    draft = parent.final_draft
    locked = [a.model_copy(deep=True) for a in draft.assignments if (a.date, a.shift) not in affected_set]
    earlier = [a.model_copy(deep=True) for a in draft.assignments
               if (a.date, a.shift) in affected_set and (a.nurse_id, a.date, a.shift) not in by_row]

    snapshot = make_snapshot(roster, rules, parent.unit, parent.week_start, snapshot_id_for(new_case_id), now)
    scheduler = make_scheduler(new_case_id, snapshot.snapshot_id)  # may fail: do it before saving anything
    if store is not None:
        store.save(building_record(snapshot, new_case_id, parent.case_id, "call_out", affected))
    try:
        child = schedule_case(scheduler, rules_checker, snapshot, demand, availability, new_case_id, parent.case_id,
                              trigger="call_out", affected_shifts=affected, store=store, locked_assignments=locked,
                              earlier_assignments=earlier, callouts=unique, extra_review=parent.input_review,
                              unusual=list(parent.unusual))
    except BaseException:
        if store is not None:
            store.discard_building(new_case_id)
        raise
    old = mark_out_of_date(parent, new_case_id)
    if store is not None:
        store.save(old)
    return old, child
