"""The orchestrator: plain code, not an AI agent. Owner: Cheich. Source of truth: the PRD.

One run:
  1. freeze one snapshot (roster, rules, unit, week),
  2. run the Demand and Availability agents at the same time (an agent that fails or returns nothing is
     retried once),
  3. check each result in code and write `status` on every row (only this code does that, never an agent).
     A result with a malformed row or a value outside the allowed lists is rejected whole, with the first
     problems named. A nurse in the availability data who is not on the roster goes to needs_manual_review,
  4. if any required row is missing, STOP before the Scheduler (outcome stopped_missing_input),
  5. otherwise run the Scheduler and Rules Checker loop (run_phase1),
  6. return one case record for the manager to review, saved after every status change when a store is given.
     Nothing is final without the manager.

Status rules (the same for both kinds of row):
  - missing: the row is absent, repeated, unreadable, or the agent failed. Never guess a value.
  - needs_review: the agent flagged doubt, or the value looks wrong to code (the nurse count does not match the
    patient ratio, or is more than 2 away from the median for that kind of shift). The value is kept.
  - ok: everything else.

Agents only get copies, so editing what they were given cannot change the snapshot.
"""

import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from pydantic import ValidationError

from app.case_store import CaseStore
from app.contract.case_record import (
    AvailabilityResult,
    CaseRecord,
    DemandResult,
    RoundSummary,
    ShiftRef,
    Snapshot,
    StatusCounts,
    VersionViolations,
)
from app.contract.models import (
    Assignment,
    AvailabilityRow,
    Callout,
    DemandRow,
    NeedsManualReview,
    Nurse,
    RulesConfig,
    _adjust_date,
)
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


def status_counts(rows: List[Any]) -> StatusCounts:
    c = StatusCounts()
    for r in rows:
        setattr(c, r.status, getattr(c, r.status) + 1)
    return c


def _index(raw: Any, key_fields: Tuple[str, ...]) -> Dict[Tuple, List[dict]]:
    """Group the agent's rows by key. Anything that is not a dict with those fields is dropped.
    A date like 2026-11-2 is read as 2026-11-02, the same way the row forms read it."""
    grouped: Dict[Tuple, List[dict]] = {}
    for r in raw if isinstance(raw, list) else []:
        if isinstance(r, dict) and all(isinstance(r.get(f), str) for f in key_fields):
            key = []
            for f in key_fields:
                try:
                    key.append(_adjust_date(r[f]) if f == "date" else r[f])
                except ValueError:
                    key.append(r[f])
            grouped.setdefault(tuple(key), []).append(r)
    return grouped


def _short(text: Any, limit: int = 160) -> str:
    one_line = " ".join(str(text).split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "\u2026"


def reject_reason(raw: Any, kind: str) -> str:
    """"" if every row is well formed. Otherwise one plain sentence naming the first problems (row number and
    field), because the PRD rejects a whole result that has a malformed row or a value outside the allowed lists.
    `kind` is "demand" or "availability". A row that leaves its numbers or flags empty is NOT malformed:
    that is how an agent says data is missing."""
    if not isinstance(raw, list):
        return "its result was rejected: it is not a list of rows"
    problems: List[str] = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            problems.append(f"row {i + 1} is not an object")
            continue
        data = {k: v for k, v in r.items() if k not in ("flag", "status")}
        try:
            try:
                (DemandRow if kind == "demand" else AvailabilityRow)(**data, status="ok")
            except ValidationError:
                if kind == "demand" or data.get("available") is not None or data.get("reason") is not None:
                    raise
                AvailabilityRow(**{**data, "status": "missing", "note": "empty"})  # empty on purpose: missing data
        except (ValidationError, TypeError) as err:
            if isinstance(err, ValidationError):
                first = err.errors()[0]
                field = ".".join(str(part) for part in first["loc"]) or "row"
                problems.append(f"row {i + 1}, field {field}: {_short(first['msg'], 100)}")
            else:
                problems.append(f"row {i + 1}: {_short(err, 100)}")
    if not problems:
        return ""
    more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
    return f"its result was rejected: {'; '.join(problems[:3])}{more}"


UNKNOWN_NURSE_NOTE = "this nurse is in the availability data but not on the roster, so was not scheduled"


def unknown_nurse_review(raw: Any, snapshot: Snapshot) -> List[NeedsManualReview]:
    """A nurse who has availability rows but no roster entry goes to needs_manual_review. Never scheduled."""
    on_roster = {n.nurse_id for n in snapshot.roster}
    stray = {r["nurse_id"] for r in raw if isinstance(r, dict) and isinstance(r.get("nurse_id"), str)
             and r["nurse_id"] not in on_roster} if isinstance(raw, list) else set()
    return [NeedsManualReview(item_type="nurse", id=n, note=UNKNOWN_NURSE_NOTE) for n in sorted(stray)]


def _flag(row: dict) -> str:
    f = row.get("flag")
    return f.strip() if isinstance(f, str) else ""


def stamp_demand(raw: Any, snapshot: Snapshot, agent_error: str = "") -> DemandResult:
    """One DemandRow for every unit, date and shift of the week, each with a status."""
    ratio = snapshot.rules.ratio_patients_per_nurse
    agent_error = agent_error or reject_reason(raw, "demand")
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
                note = (f"{_nurses(row.nurses_needed)} for {row.patient_count} patients does not match "
                        f"the ratio of {ratio} patients per nurse (expected {expected})")
            if note:
                row = row.model_copy(update={"status": "needs_review", "note": note})
            rows.append(row)
    rows = _flag_outliers(rows)
    return DemandResult(rows=rows, counts=status_counts(rows))


def _nurses(n: int) -> str:
    return f"{n} nurse" if n == 1 else f"{n} nurses"


def _flag_outliers(rows: List[DemandRow]) -> List[DemandRow]:
    """A row more than 2 nurses from the median for its kind of shift becomes needs_review (value kept).
    Needs at least 3 numbers for that kind of shift to have a median worth comparing to."""
    flagged = list(rows)
    for shift in SHIFTS:
        values = [r.nurses_needed for r in rows if r.shift == shift and r.nurses_needed is not None]
        if len(values) < 3:
            continue
        median = statistics.median(values)
        for i, r in enumerate(flagged):
            if r.shift == shift and r.nurses_needed is not None and abs(r.nurses_needed - median) > 2:
                note = f"{_nurses(r.nurses_needed)} is more than 2 away from the {shift}-shift median of {median:g}"
                flagged[i] = r.model_copy(update={"status": "needs_review",
                                                  "note": f"{r.note}; {note}" if r.note else note})
    return flagged


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

    The leave cross-check: approved leave is a fact from Shift Board, so if it covers the day but the agent says
    "available", code sets the row to unavailable (available False, reason approved_time_off) and marks it
    needs_review with a note saying so. This is the one place code overrides an agent's value: otherwise the
    nurse would stay bookable and check_rules, which reads only this row, would pass a draft that schedules them."""
    time_off = approved_leave_days(leave)
    agent_error = agent_error or reject_reason(raw, "availability")
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
                    clash = (f"the agent marked this nurse available, but approved {kind} leave covers this day, "
                             "so the row was set to unavailable")
                    note = f"{note}; {clash}" if note else clash
                    row = row.model_copy(update={"available": False, "reason": "approved_time_off"})
                if note:
                    row = row.model_copy(update={"status": "needs_review", "note": note})
                rows.append(row)
    return AvailabilityResult(rows=rows, counts=status_counts(rows))


def _run_agent(agent: Any, snapshot: Snapshot, tries: int = 2) -> Tuple[Any, str]:
    """Run one agent on its own copy of the snapshot. A failure, or a result with no rows, is retried once;
    after that it becomes an error message, never a crash and never a guess."""
    error = ""
    for _ in range(tries):
        try:
            result = agent.run(snapshot.model_copy(deep=True))
        except Exception as err:
            error = str(err) or type(err).__name__
            continue
        if result is None or result == []:
            error = "it returned no rows"
            continue
        return result, ""
    return None, f"{error} (after {tries} tries)"


def make_snapshot(roster: List[Nurse], rules: RulesConfig, unit: str, week_start: str,
                  snapshot_id: str, now: Optional[Callable[[], datetime]] = None) -> Snapshot:
    stamp = (now or datetime.now)().isoformat(timespec="seconds")
    return Snapshot(snapshot_id=snapshot_id, unit=unit, week_start=week_start, created_at=stamp,
                    roster=roster, rules=rules)


def all_shifts(week_start: str) -> List[ShiftRef]:
    return [ShiftRef(date=day, shift=shift) for day in week_dates(week_start) for shift in SHIFTS]


def _missing_input(demand: DemandResult, availability: AvailabilityResult) -> Tuple[str, List[NeedsManualReview]]:
    """What is missing, in plain language, and one needs-manual-review row for each missing demand shift and nurse."""
    gone_d = [r for r in demand.rows if r.status == "missing"]
    gone_a = [r for r in availability.rows if r.status == "missing"]
    review = [NeedsManualReview(item_type="demand_day", id=f"{r.date} {r.shift}", note=r.note) for r in gone_d]
    seen = set()
    for r in gone_a:
        if r.nurse_id not in seen:
            seen.add(r.nurse_id)
            review.append(NeedsManualReview(item_type="nurse", id=r.nurse_id, note=r.note))
    parts = []
    if gone_d:
        parts.append(f"{len(gone_d)} demand row(s)")
    if gone_a:
        parts.append(f"{len(gone_a)} availability row(s)")
    first = (gone_d or gone_a)[0].note
    return (f"Stopped before scheduling because required input is missing: {' and '.join(parts)}. "
            f"First problem: {first}."), review


def schedule_case(scheduler: Scheduler, rules_checker: RulesChecker, snapshot: Snapshot, demand: DemandResult,
                  availability: AvailabilityResult, case_id: str, parent_case_id: Optional[str] = None,
                  trigger: str = "weekly", affected_shifts: Optional[List[ShiftRef]] = None,
                  extra_review: Optional[List[NeedsManualReview]] = None,
                  store: Optional[CaseStore] = None, locked_assignments: Optional[List[Assignment]] = None,
                  earlier_assignments: Optional[List[Assignment]] = None,
                  callouts: Optional[List[Callout]] = None) -> CaseRecord:
    """Build the case record for stamped rows. If any required row is missing, STOP before the Scheduler runs
    (outcome stopped_missing_input, no drafts) and tell the manager what is missing, as the PRD says. Otherwise
    run the Scheduler and Rules Checker loop. The Scheduler must be built with snapshot.snapshot_id.
    `extra_review` rows (such as a nurse not on the roster) are added to needs_manual_review. The finished
    record is saved to `store` when one is given. Used by run_case and by a manager's demand change."""
    record = _schedule(scheduler, rules_checker, snapshot, demand, availability, case_id, parent_case_id,
                       trigger, affected_shifts, list(extra_review or []), locked_assignments or [],
                       earlier_assignments or [], callouts or [])
    if store is not None:
        store.save(record)
    return record


def _schedule(scheduler: Scheduler, rules_checker: RulesChecker, snapshot: Snapshot, demand: DemandResult,
              availability: AvailabilityResult, case_id: str, parent_case_id: Optional[str], trigger: str,
              affected_shifts: Optional[List[ShiftRef]], extra: List[NeedsManualReview],
              locked: List[Assignment], earlier: List[Assignment], callouts: List[Callout]) -> CaseRecord:
    common = dict(
        case_id=case_id, snapshot_id=snapshot.snapshot_id, start_time=snapshot.created_at, trigger=trigger,
        affected_shifts=affected_shifts if affected_shifts is not None else all_shifts(snapshot.week_start),
        parent_case_id=parent_case_id, unit=snapshot.unit, week_start=snapshot.week_start,
        status="waiting_approval", demand_result=demand, availability_result=availability, callouts=callouts,
    )
    if demand.counts.missing or availability.counts.missing:
        reason, review = _missing_input(demand, availability)
        return CaseRecord(**common, outcome="stopped_missing_input", stop_reason=reason,
                          needs_manual_review=review + extra)

    call_out = trigger == "call_out"
    inputs = Phase1Inputs(demand=demand.rows, availability=availability.rows,
                          roster=snapshot.roster, rules=snapshot.rules,
                          locked_assignments=locked if call_out else [],
                          affected_shifts=common["affected_shifts"] if call_out else [],
                          earlier_assignments=earlier if call_out else [])
    result = run_phase1(scheduler, rules_checker, inputs, case_id=case_id, snapshot_id=snapshot.snapshot_id)
    return CaseRecord(
        **common, outcome=result.outcome, rounds_used=min(len(result.rounds), 3),
        rounds=[RoundSummary(**r.model_dump()) for r in result.rounds],
        drafts=result.drafts, violations=[VersionViolations(version=v, violations=vs)
                                          for v, vs in result.round_violations],
        final_draft=result.final_draft, open_violations=result.open_violations,
        soft_tradeoffs=result.soft_tradeoffs, unfixable=result.unfixable,
        needs_manual_review=result.needs_manual_review + extra,
    )


def building_record(snapshot: Snapshot, case_id: str, parent_case_id: Optional[str] = None,
                    trigger: str = "weekly", affected_shifts: Optional[List[ShiftRef]] = None) -> CaseRecord:
    """The first saved state of a run: status building, no results yet."""
    return CaseRecord(
        case_id=case_id, snapshot_id=snapshot.snapshot_id, start_time=snapshot.created_at, trigger=trigger,
        affected_shifts=affected_shifts if affected_shifts is not None else all_shifts(snapshot.week_start),
        parent_case_id=parent_case_id, unit=snapshot.unit, week_start=snapshot.week_start, status="building",
        demand_result=DemandResult(rows=[], counts=StatusCounts()),
        availability_result=AvailabilityResult(rows=[], counts=StatusCounts()),
    )


def run_case(demand_agent: DemandAgent, availability_agent: AvailabilityAgent, scheduler: Scheduler,
             rules_checker: RulesChecker, roster: List[Nurse], rules: RulesConfig, unit: str,
             week_start: str, case_id: str, parent_case_id: Optional[str] = None,
             now: Optional[Callable[[], datetime]] = None, snapshot_id: Optional[str] = None,
             leave: Optional[List[Dict[str, Any]]] = None, store: Optional[CaseStore] = None) -> CaseRecord:
    """`snapshot_id` defaults to snapshot_id_for(case_id). The Scheduler must be built with the same ID,
    or its drafts are rejected as mislabeled. `leave` is the Shift Board leave list (leave.json); approved
    requests are cross-checked against the Availability agent's rows. With a `store`, the record is saved as
    `building` before the agents run and again when the run finishes (every status change is on disk)."""
    snapshot = make_snapshot(roster, rules, unit, week_start, snapshot_id or snapshot_id_for(case_id), now)
    if store is not None:
        store.save(building_record(snapshot, case_id, parent_case_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        demand_job = pool.submit(_run_agent, demand_agent, snapshot)
        availability_job = pool.submit(_run_agent, availability_agent, snapshot)
        demand_raw, demand_err = demand_job.result()
        availability_raw, availability_err = availability_job.result()

    demand = stamp_demand(demand_raw, snapshot, demand_err)
    availability = stamp_availability(availability_raw, snapshot, availability_err, leave)

    extra = unknown_nurse_review(availability_raw, snapshot) if not availability_err else []
    return schedule_case(scheduler, rules_checker, snapshot, demand, availability, case_id, parent_case_id,
                         extra_review=extra, store=store)
