"""The orchestrator: plain code, not an AI agent. Owner: Cheich. Source of truth: the PRD.

One run:
  1. freeze one snapshot (roster, rules, unit, week),
  2. run the Demand and Availability agents at the same time,
  3. write `status` on every row (only this code does that, never an agent),
  4. run the Scheduler and Rules Checker loop (run_phase1),
  5. return one case record for the manager to review. Nothing is final without the manager.

Status rules (the same for both kinds of row):
  - missing: the row is absent, repeated, unreadable, or the agent failed. Never guess a value.
  - needs_review: the agent flagged doubt, or the value looks wrong to code. The value is kept.
  - ok: everything else.

Agents only get copies, so editing what they were given cannot change the snapshot.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from pydantic import ValidationError

from app.contract.case_record import (
    AvailabilityResult,
    CaseRecord,
    DemandResult,
    RoundSummary,
    Snapshot,
    StatusCounts,
)
from app.contract.models import AvailabilityRow, DemandRow, Nurse, RulesConfig
from app.harness.phase1 import Phase1Inputs, RulesChecker, Scheduler, run_phase1

SHIFTS = ("day", "night")


class DemandAgent(Protocol):
    def run(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        """Rows with unit, date, shift, patient_count, nurses_needed, and an optional `flag` (text)."""


class AvailabilityAgent(Protocol):
    def run(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        """Rows with nurse_id, date, shift, available, reason, and an optional `flag` (text)."""


def snapshot_id_for(case_id: str) -> str:
    """The snapshot ID a case uses. Build the Scheduler with this, so its drafts carry the right label."""
    return f"snap-{case_id}"


def week_dates(week_start: str) -> List[str]:
    start = date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def _counts(rows: List[Any]) -> StatusCounts:
    c = StatusCounts()
    for r in rows:
        setattr(c, r.status, getattr(c, r.status) + 1)
    return c


def _index(raw: Any, key_fields: Tuple[str, ...]) -> Dict[Tuple, List[dict]]:
    """Group the agent's rows by key. Anything that is not a dict with those fields is dropped."""
    grouped: Dict[Tuple, List[dict]] = {}
    for r in raw if isinstance(raw, list) else []:
        if isinstance(r, dict) and all(isinstance(r.get(f), str) for f in key_fields):
            grouped.setdefault(tuple(r[f] for f in key_fields), []).append(r)
    return grouped


def _flag(row: dict) -> str:
    f = row.get("flag")
    return f.strip() if isinstance(f, str) else ""


def stamp_demand(raw: Any, snapshot: Snapshot, agent_error: str = "") -> DemandResult:
    """One DemandRow for every unit, date and shift of the week, each with a status."""
    ratio = snapshot.rules.ratio_patients_per_nurse
    found = _index(raw, ("unit", "date", "shift")) if not agent_error else {}
    rows: List[DemandRow] = []
    for day in week_dates(snapshot.week_start):
        for shift in SHIFTS:
            base = dict(unit=snapshot.unit, date=day, shift=shift)
            why = agent_error and f"the Demand agent failed: {agent_error}"
            candidates = found.get((snapshot.unit, day, shift), [])
            if not why and not candidates:
                why = "the Demand agent returned no row for this shift"
            elif not why and len(candidates) > 1:
                why = "the Demand agent returned more than one row for this shift"
            row = None
            if not why:
                c = candidates[0]
                try:
                    row = DemandRow(**base, patient_count=c.get("patient_count"),
                                    nurses_needed=c.get("nurses_needed"), status="ok")
                    if row.patient_count is None or row.nurses_needed is None:
                        why = "the Demand agent left out a number"
                except (ValidationError, TypeError) as err:
                    why = f"the Demand agent's row could not be read: {str(err).splitlines()[0]}"
            if why:
                rows.append(DemandRow(**base, status="missing", note=why))
                continue
            note = _flag(candidates[0])
            expected = math.ceil(row.patient_count / ratio)
            if not note and row.nurses_needed != expected:
                note = (f"{row.nurses_needed} nurses for {row.patient_count} patients does not match "
                        f"the ratio of {ratio} patients per nurse (expected {expected})")
            if note:
                row = row.model_copy(update={"status": "needs_review", "note": note})
            rows.append(row)
    return DemandResult(rows=rows, counts=_counts(rows))


def approved_leave_days(leave: Optional[List[Dict[str, Any]]]) -> Dict[Tuple[str, str], str]:
    """(nurse_id, date) -> leave type, for approved Shift Board leave requests only. Pending, denied
    and unreadable requests are ignored: they are not time off."""
    days: Dict[Tuple[str, str], str] = {}
    for req in leave or []:
        try:
            if req.get("status") != "approved":
                continue
            first, last = date.fromisoformat(req["start"]), date.fromisoformat(req["end"])
            for i in range((last - first).days + 1):
                days[(req["employeeId"], (first + timedelta(days=i)).isoformat())] = str(req.get("type", "leave"))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return days


def stamp_availability(raw: Any, snapshot: Snapshot, agent_error: str = "",
                       leave: Optional[List[Dict[str, Any]]] = None) -> AvailabilityResult:
    """One AvailabilityRow for every nurse, date and shift of the week, each with a status.

    The leave cross-check: if approved leave covers the day but the agent says "available", the row
    becomes needs_review (the agent's value is kept, as the rules say). Code never trusts the agent alone."""
    time_off = approved_leave_days(leave)
    found = _index(raw, ("nurse_id", "date", "shift")) if not agent_error else {}
    rows: List[AvailabilityRow] = []
    for nurse in snapshot.roster:
        for day in week_dates(snapshot.week_start):
            for shift in SHIFTS:
                base = dict(nurse_id=nurse.nurse_id, date=day, shift=shift)
                why = agent_error and f"the Availability agent failed: {agent_error}"
                candidates = found.get((nurse.nurse_id, day, shift), [])
                if not why and not candidates:
                    why = "the Availability agent returned no row for this nurse and shift"
                elif not why and len(candidates) > 1:
                    why = "the Availability agent returned more than one row for this nurse and shift"
                row = None
                if not why:
                    c = candidates[0]
                    try:
                        row = AvailabilityRow(**base, available=c.get("available"),
                                              reason=c.get("reason"), status="ok")
                    except (ValidationError, TypeError) as err:
                        why = f"the Availability agent's row could not be read: {str(err).splitlines()[0]}"
                if why:
                    rows.append(AvailabilityRow(**base, status="missing", note=why))
                    continue
                note = _flag(candidates[0])
                if not note and row.available and row.reason != "none":
                    note = f"marked available but the reason is {row.reason}"
                kind = time_off.get((nurse.nurse_id, day))
                if kind and row.available:
                    clash = f"marked available but approved {kind} leave covers this day"
                    note = f"{note}; {clash}" if note else clash
                if note:
                    row = row.model_copy(update={"status": "needs_review", "note": note})
                rows.append(row)
    return AvailabilityResult(rows=rows, counts=_counts(rows))


def _run_agent(agent: Any, snapshot: Snapshot) -> Tuple[Any, str]:
    """Run one agent on its own copy of the snapshot. A failure becomes an error message, not a crash."""
    try:
        return agent.run(snapshot.model_copy(deep=True)), ""
    except Exception as err:
        return None, str(err) or type(err).__name__


def make_snapshot(roster: List[Nurse], rules: RulesConfig, unit: str, week_start: str,
                  snapshot_id: str, now: Optional[Callable[[], datetime]] = None) -> Snapshot:
    stamp = (now or datetime.now)().isoformat(timespec="seconds")
    return Snapshot(snapshot_id=snapshot_id, unit=unit, week_start=week_start, created_at=stamp,
                    roster=roster, rules=rules)


def run_case(demand_agent: DemandAgent, availability_agent: AvailabilityAgent, scheduler: Scheduler,
             rules_checker: RulesChecker, roster: List[Nurse], rules: RulesConfig, unit: str,
             week_start: str, case_id: str, parent_case_id: Optional[str] = None,
             now: Optional[Callable[[], datetime]] = None, snapshot_id: Optional[str] = None,
             leave: Optional[List[Dict[str, Any]]] = None) -> CaseRecord:
    """`snapshot_id` defaults to snapshot_id_for(case_id). The Scheduler must be built with the same ID,
    or its drafts are rejected as mislabeled. `leave` is the Shift Board leave list (leave.json); approved
    requests are cross-checked against the Availability agent's rows."""
    snapshot = make_snapshot(roster, rules, unit, week_start, snapshot_id or snapshot_id_for(case_id), now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        demand_job = pool.submit(_run_agent, demand_agent, snapshot)
        availability_job = pool.submit(_run_agent, availability_agent, snapshot)
        demand_raw, demand_err = demand_job.result()
        availability_raw, availability_err = availability_job.result()

    demand = stamp_demand(demand_raw, snapshot, demand_err)
    availability = stamp_availability(availability_raw, snapshot, availability_err, leave)

    inputs = Phase1Inputs(demand=demand.rows, availability=availability.rows,
                          roster=snapshot.roster, rules=snapshot.rules)
    result = run_phase1(scheduler, rules_checker, inputs, case_id=case_id, snapshot_id=snapshot.snapshot_id)

    return CaseRecord(
        case_id=case_id, parent_case_id=parent_case_id, snapshot_id=snapshot.snapshot_id, unit=unit,
        week_start=week_start, created_at=snapshot.created_at,
        state="awaiting_approval" if result.final_draft is not None else "failed",
        outcome=result.outcome if result.final_draft is not None else None,
        demand_result=demand, availability_result=availability,
        rounds=[RoundSummary(**r.model_dump()) for r in result.rounds],
        final_draft=result.final_draft, open_violations=result.open_violations,
        soft_tradeoffs=result.soft_tradeoffs, unfixable=result.unfixable,
        needs_manual_review=result.needs_manual_review,
    )
