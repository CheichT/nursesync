"""Starting a weekly run from the API. Owner: Cheich. Version 0.

A weekly run calls the live agents (about $0.50 to $1.50 and a few minutes), so it:
  - runs in a background thread: `start` returns at once and the caller polls `status` (or the case itself, which is
    saved as `building` first and becomes `waiting_approval` when done),
  - runs ONE AT A TIME: a second start is refused while one is in progress,
  - is counted against the daily cap (usage.py) only after its inputs checked out, before any money is spent,
  - removes its unfinished case if it fails, and a stale `building` case left by a crash is swept at startup.

The inputs (roster, rules, approved leave) come from `load_run_inputs`. For now that is the mock data, so only unit 7W and
the week of 2026-11-02 exist; a real Shift Board source replaces it later.
"""

import json
import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.case_store import CaseStore
from app.contract.case_record import CaseRecord
from app.contract.models import Form, Nurse, RulesConfig
from app.decisions import DecisionRefused, SchedulerFactory
from app.harness.phase1 import DEFAULT_DATA, RulesChecker, load_inputs
from app.orchestrator import run_case, snapshot_id_for
from app.usage import UsageMeter

log = logging.getLogger("nursesync.runs")

MAX_REMEMBERED_RUNS = 50
STALE_AFTER_MINUTES = 30


class RunRefused(Exception):
    """The request cannot start a run (a bad unit or week). The message is plain language."""


@dataclass
class RunInputs:
    roster: List[Nurse]
    rules: RulesConfig
    leave: List[Dict[str, Any]]


class RunStatus(Form):
    run_id: str  # the same as case_id
    case_id: str
    state: str  # running, done or failed
    started_at: str
    finished_at: Optional[str] = None
    outcome: Optional[str] = None  # when done: the case outcome (passed, stopped_after_3_rounds, stopped_missing_input)
    message: str = ""


def mock_run_inputs(unit: str, week_start: str) -> RunInputs:
    """Validate (unit, week_start) against the mock data and return the inputs for a run."""
    inputs = load_inputs()
    units = sorted({n.unit for n in inputs.roster})
    if unit not in units:
        raise RunRefused(f"Unknown unit {unit!r}. Known units: {', '.join(units)}.")
    try:
        start = date.fromisoformat(week_start)
    except (TypeError, ValueError):
        raise RunRefused("week_start must be a date like 2026-11-02.")
    if start.weekday() != 0:
        raise RunRefused(f"{week_start} is not a Monday. A week starts on a Monday.")
    covered = min(r.date for r in inputs.demand)
    if week_start != covered:
        raise RunRefused(f"There is no data for the week of {week_start}. The sample data covers the week of {covered}.")
    return RunInputs(roster=inputs.roster, rules=inputs.rules,
                     leave=json.loads((DEFAULT_DATA / "leave.json").read_text()))


class RunManager:
    def __init__(self, store: CaseStore, make_demand_agent: Callable[[], Any], make_availability_agent: Callable[[], Any],
                 make_scheduler: SchedulerFactory, rules_checker: RulesChecker,
                 load_run_inputs: Callable[[str, str], RunInputs] = mock_run_inputs,
                 usage: Optional[UsageMeter] = None, clock: Optional[Callable[[], datetime]] = None):
        self.store, self.usage = store, usage
        self._make_demand, self._make_availability = make_demand_agent, make_availability_agent
        self._make_scheduler, self._checker, self._load = make_scheduler, rules_checker, load_run_inputs
        self._clock = clock or datetime.now
        self._busy = threading.Lock()
        self._guard = threading.Lock()
        self._runs: Dict[str, RunStatus] = {}
        self._events: Dict[str, threading.Event] = {}

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    def start(self, unit: str, week_start: str, case_id: Optional[str] = None) -> RunStatus:
        """Check everything cheap, then take the one run slot, count one paid operation, and start the run."""
        inputs = self._load(unit, week_start)  # raises RunRefused
        case_id = case_id or f"run-{unit}-{week_start}-{self._clock():%H%M%S}-{secrets.token_hex(2)}"
        if self.store.exists(case_id):  # also refuses an invalid case id
            raise DecisionRefused(f"A case with id {case_id} already exists.")
        if not self._busy.acquire(blocking=False):
            raise DecisionRefused("A weekly run is already in progress. Wait for it to finish, then try again.")
        try:
            if self.usage is not None:
                self.usage.try_spend("weekly_run", case_id)
        except BaseException:
            self._busy.release()
            raise
        status = RunStatus(run_id=case_id, case_id=case_id, state="running", started_at=self._now())
        with self._guard:
            self._runs[case_id] = status
            self._events[case_id] = threading.Event()
            for old in list(self._runs)[:-MAX_REMEMBERED_RUNS]:
                self._runs.pop(old, None)
                self._events.pop(old, None)
        threading.Thread(target=self._work, args=(case_id, unit, week_start, inputs), daemon=True).start()
        return status.model_copy()

    def _work(self, case_id: str, unit: str, week_start: str, inputs: RunInputs) -> None:
        try:
            record: CaseRecord = run_case(
                self._make_demand(), self._make_availability(),
                self._make_scheduler(case_id, snapshot_id_for(case_id)), self._checker,
                inputs.roster, inputs.rules, unit, week_start, case_id, leave=inputs.leave, store=self.store)
            update = dict(state="done", outcome=record.outcome)
        except Exception:
            log.exception("weekly run %s failed", case_id)  # the detail stays in the server log
            update = dict(state="failed", message="The run failed before it finished, so no case was saved. "
                                                  "Check the server log, then try again.")
        finally:
            self._busy.release()
        with self._guard:
            self._runs[case_id] = self._runs[case_id].model_copy(update={**update, "finished_at": self._now()})
            self._events[case_id].set()

    def status(self, run_id: str) -> Optional[RunStatus]:
        with self._guard:
            found = self._runs.get(run_id)
            return found.model_copy() if found else None

    def wait(self, run_id: str, timeout: float = 30.0) -> bool:
        """For tests: block until the run finishes."""
        with self._guard:
            event = self._events.get(run_id)
        return bool(event and event.wait(timeout))

    def active_ids(self) -> List[str]:
        with self._guard:
            return [r.case_id for r in self._runs.values() if r.state == "running"]

    def sweep(self) -> int:
        return sweep_stale(self.store, active_ids=self.active_ids(), now=self._clock())


def sweep_stale(store: CaseStore, older_than_minutes: int = STALE_AFTER_MINUTES, active_ids: Optional[List[str]] = None,
                now: Optional[datetime] = None) -> int:
    """Remove cases left in `building` by a crash. A case that is still running, or is recent, is kept."""
    now = now or datetime.now()
    removed = 0
    for case_id in store.list_ids():
        if case_id in (active_ids or []):
            continue
        try:
            record = store.load(case_id)
            if record.status == "building" and now - datetime.fromisoformat(record.start_time) > timedelta(minutes=older_than_minutes):
                removed += store.discard_building(case_id)
        except Exception:  # an unreadable or odd file is left alone, and reported by the case list
            continue
    return removed
