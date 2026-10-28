"""The manager's decisions on a case: approve, reject, change demand, and mark out of date. Owner: Cheich.

Source of truth: docs/approval-view-v0.md (Kerrian) and the PRD. Every function takes a case record and
returns a NEW one; nothing is changed in place and nothing is saved here (use CaseStore). A case can only be
decided while it is `awaiting_approval`. A refusal is a DecisionRefused with a message safe to show the manager.

There is no login in version one, so a decision records WHAT was decided and WHEN, not who.
"""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.contract.case_record import CaseRecord, DecisionDetails, DemandChange, DemandResult
from app.contract.models import DemandRow, Nurse, RulesConfig
from app.harness.phase1 import RulesChecker, Scheduler
from app.orchestrator import make_snapshot, schedule_case, snapshot_id_for, status_counts

SchedulerFactory = Callable[[str, str], Scheduler]  # (case_id, snapshot_id) -> a Scheduler built with both


class DecisionRefused(Exception):
    """The decision is not allowed. The message says why in plain language."""


def _stamp(now: Optional[Callable[[], datetime]]) -> str:
    return (now or datetime.now)().isoformat(timespec="seconds")


def _check_open(record: CaseRecord) -> None:
    if record.status == "waiting_approval":
        return
    if record.status == "out_of_date":
        newer = f" Review case {record.newer_case_id} instead." if record.newer_case_id else ""
        raise DecisionRefused(f"This draft is out of date: a newer one exists.{newer}")
    if record.status == "building":
        raise DecisionRefused("This case is still running.")
    raise DecisionRefused(f"This case is already {record.status}. A decided case cannot be changed.")


def has_open_issues(record: CaseRecord) -> bool:
    """True if the draft still has hard violations, unfixable rows, or shifts left unstaffed."""
    return bool(record.open_violations or record.unfixable or (record.final_draft and record.final_draft.open_gaps))


def approve(record: CaseRecord, acknowledge_open_issues: bool = False,
            now: Optional[Callable[[], datetime]] = None) -> CaseRecord:
    """Approve the draft. A draft with open issues needs `acknowledge_open_issues=True`, which is saved.
    A case with no valid draft (stopped for missing input, or no round gave a valid draft) cannot be approved."""
    _check_open(record)
    if record.final_draft is None:
        raise DecisionRefused(record.stop_reason or "No valid draft was produced, so there is nothing to approve. "
                              "Change a demand number, or reject and build the week by hand.")
    if has_open_issues(record) and not acknowledge_open_issues:
        raise DecisionRefused("This draft still has open issues (rule violations, unfixable rows or unstaffed "
                              "shifts). Approve only after confirming you accept them.")
    details = DecisionDetails(action="approve", acknowledged_open_issues=has_open_issues(record))
    return record.model_copy(update={"status": "approved", "manager_decision": "approved",
                                     "decision_time": _stamp(now), "decision_details": details})


def reject(record: CaseRecord, now: Optional[Callable[[], datetime]] = None) -> CaseRecord:
    """Reject ends the case with the outcome "rejected"; the manager builds the week by hand."""
    _check_open(record)
    return record.model_copy(update={"status": "rejected", "outcome": "rejected", "manager_decision": "rejected",
                                     "decision_time": _stamp(now), "decision_details": DecisionDetails(action="reject")})


def mark_out_of_date(record: CaseRecord, newer_case_id: str) -> CaseRecord:
    """A newer run replaced this one (for example a late call-out). Only an undecided case can be replaced."""
    _check_open(record)
    return record.model_copy(update={"status": "out_of_date", "newer_case_id": newer_case_id})


def change_demand(record: CaseRecord, changes: List[DemandChange], new_case_id: str,
                  make_scheduler: SchedulerFactory, rules_checker: RulesChecker, roster: List[Nurse],
                  rules: RulesConfig, now: Optional[Callable[[], datetime]] = None) -> Tuple[CaseRecord, CaseRecord]:
    """Set nurses_needed on one or more rows, then rerun the Scheduler loop only (availability is kept).

    Returns (old_case, new_case). The new case is a child of the old one with its own snapshot; the old case
    becomes out_of_date with the decision recorded. Rows the manager sets become `ok` with a plain note.
    """
    _check_open(record)
    if not changes:
        raise DecisionRefused("No demand changes were given.")
    seen = set()
    for c in changes:
        key = (c.unit, c.date, c.shift)
        if key in seen:
            raise DecisionRefused(f"More than one change for {c.date} {c.shift}.")
        seen.add(key)
    by_key: Dict[Tuple[str, str, str], DemandRow] = {(r.unit, r.date, r.shift): r for r in record.demand_result.rows}
    unknown = [k for k in seen if k not in by_key]
    if unknown:
        raise DecisionRefused(f"There is no demand row for {unknown[0][1]} {unknown[0][2]} on unit {unknown[0][0]}.")

    new_rows: List[DemandRow] = []
    for row in record.demand_result.rows:
        change = next((c for c in changes if (c.unit, c.date, c.shift) == (row.unit, row.date, row.shift)), None)
        if change is None:
            new_rows.append(row.model_copy(deep=True))
            continue
        was = "missing" if row.nurses_needed is None else str(row.nurses_needed)
        new_rows.append(DemandRow(unit=row.unit, date=row.date, shift=row.shift, patient_count=row.patient_count,
                                  nurses_needed=change.nurses_needed, status="ok",
                                  note=f"set by manager (was {was})"))
    demand = DemandResult(rows=new_rows, counts=status_counts(new_rows))

    snapshot = make_snapshot(roster, rules, record.unit, record.week_start, snapshot_id_for(new_case_id), now)
    child = schedule_case(make_scheduler(new_case_id, snapshot.snapshot_id), rules_checker, snapshot, demand,
                          record.availability_result.model_copy(deep=True), new_case_id, record.case_id)
    details = DecisionDetails(action="change_demand", demand_changes=list(changes), new_case_id=new_case_id)
    old = record.model_copy(update={"status": "out_of_date", "newer_case_id": new_case_id,
                                    "decision_time": _stamp(now), "decision_details": details})
    return old, child

