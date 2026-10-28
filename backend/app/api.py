"""A small local HTTP API over the case store and the manager decisions. Owner: Cheich. Version 0.

It only wraps code that already exists and is tested (decisions.py, case_store.py). The safety rules live there, not
here: approving an out-of-date case, a case with no draft, or a draft with open issues and no acknowledgement is
refused by decisions.py, and this layer turns the refusal into a 409 with a message safe to show the manager.

THERE IS NO LOGIN. It is meant to run on this computer only (see serve.py: it binds to 127.0.0.1) and must not be
described as secure. Real sign-in comes later.

"Local only" does not stop a web page in the manager's browser from calling 127.0.0.1, so there are three guards:
  - the Host header must be 127.0.0.1 or localhost (stops DNS rebinding),
  - a POST that carries an Origin header from anywhere but the local dev origin is refused (stops cross-site posts),
  - every POST must say Content-Type: application/json (a cross-site page cannot send that without a preflight).

Change demand and call-outs rerun the live Scheduler (cents to about a dollar, and it can take minutes), so it only works when
the server was started with live agents enabled. Otherwise it answers 503 before touching anything.
"""

import logging
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field

from app.case_store import CaseNotFound, CaseStore, CaseStoreError, InvalidCaseId
from app.contract.case_record import CaseRecord, DemandChange
from app.callouts import check_call_outs, run_call_out
from app.contract.models import Callout, Form, ShiftKind
from app.decisions import DecisionRefused, SchedulerFactory, approve, change_demand, check_demand_changes, reject
from app.harness.phase1 import RulesChecker, load_inputs
from app.runs import RunManager, RunRefused, RunStatus
from app.usage import SpendCapReached, UsageMeter

log = logging.getLogger("nursesync.api")

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the Vite dev server
LOCAL_HOSTS = ["127.0.0.1", "localhost", "[::1]"]


class ApproveBody(Form):
    acknowledge_open_issues: bool = False  # the body itself is optional: no body means False


class ChangeDemandBody(Form):
    changes: List[DemandChange] = Field(min_length=1)
    new_case_id: Optional[str] = None


class CallOutItem(Form):
    nurse_id: str
    date: str
    shift: ShiftKind
    reported_at: Optional[str] = None  # ISO date and time; the server uses "now" when left out


class CallOutBody(Form):
    call_outs: List[CallOutItem] = Field(min_length=1, max_length=20)
    new_case_id: Optional[str] = None


class StartRunBody(Form):
    unit: str
    week_start: str
    case_id: Optional[str] = None


class CaseSummary(Form):
    case_id: str
    status: str
    outcome: Optional[str] = None
    unit: str
    week_start: str
    start_time: str
    trigger: str
    parent_case_id: Optional[str] = None
    newer_case_id: Optional[str] = None


class CaseList(Form):
    cases: List[CaseSummary]
    unreadable: List[Dict[str, str]] = Field(default_factory=list)


class ChangeDemandResult(Form):
    old: CaseRecord
    child: CaseRecord


def _message(text: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": text})


def create_app(store: CaseStore, scheduler_factory: Optional[SchedulerFactory] = None,
               rules_checker: Optional[RulesChecker] = None,
               load_roster_and_rules: Callable[[], Any] = load_inputs,
               allowed_origins: Optional[List[str]] = None, allowed_hosts: Optional[List[str]] = None,
               run_manager: Optional[RunManager] = None, usage: Optional[UsageMeter] = None) -> FastAPI:
    """`scheduler_factory` and `rules_checker` are the live agents (or scripted ones in tests). Without them, change
    demand is switched off. `load_roster_and_rules` returns something with .roster and .rules (mock data for now,
    Shift Board later). `run_manager` starts weekly runs (without it, starting a run is switched off). `usage` is the
    daily cap on paid operations (weekly runs and demand changes); without it there is no cap."""
    app = FastAPI(title="NurseSync case API", version="0")
    origins = allowed_origins if allowed_origins is not None else DEV_ORIGINS
    live = scheduler_factory is not None and rules_checker is not None
    case_locks: Dict[str, threading.Lock] = {}
    registry = threading.Lock()

    @contextmanager
    def one_at_a_time(case_id: str) -> Iterator[None]:
        """One request at a time per case, so two clicks cannot both decide it. A second request does not wait
        (a demand change can take minutes): it is refused at once with a plain message."""
        with registry:
            lock = case_locks.setdefault(case_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise DecisionRefused("Another request is already changing this case. Wait for it to finish, then reload.")
        try:
            yield
        finally:
            lock.release()

    @app.middleware("http")
    async def guard_posts(request: Request, call_next: Callable[..., Any]) -> Any:
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin is not None and origin not in origins:  # includes the literal "null" a sandboxed page sends
                return _message("This request came from a web page that is not allowed to use this API.", 403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return _message("Send Content-Type: application/json.", 415)
        return await call_next(request)

    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts if allowed_hosts is not None else LOCAL_HOSTS)

    @app.exception_handler(DecisionRefused)
    async def _refused(_: Request, err: DecisionRefused) -> JSONResponse:
        return _message(str(err), 409)

    @app.exception_handler(RunRefused)
    async def _bad_run(_: Request, err: RunRefused) -> JSONResponse:
        return _message(str(err), 422)

    @app.exception_handler(SpendCapReached)
    async def _cap(_: Request, err: SpendCapReached) -> JSONResponse:
        return _message(str(err), 429)

    @app.exception_handler(CaseNotFound)
    async def _missing(_: Request, err: CaseNotFound) -> JSONResponse:
        return _message(str(err), 404)

    @app.exception_handler(InvalidCaseId)
    async def _bad_id(_: Request, err: InvalidCaseId) -> JSONResponse:
        return _message(str(err), 422)

    @app.exception_handler(CaseStoreError)
    async def _store(_: Request, err: CaseStoreError) -> JSONResponse:
        return _message(str(err), 409)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, err: Exception) -> JSONResponse:
        log.exception("unexpected error")  # the detail stays in the server log, never in the response
        return _message("Something went wrong on the server. Nothing was changed by this request.", 500)

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "live_agents": live}

    @app.get("/api/usage")
    def get_usage() -> Dict[str, Any]:
        if usage is None:
            return {"capped": False, "used_today": 0, "max_per_day": None, "remaining": None, "date": None}
        return {"capped": True, **usage.snapshot()}

    @app.post("/api/runs", response_model=RunStatus, status_code=202)
    def start_run(body: StartRunBody) -> Any:
        if run_manager is None:
            return _message("Live agents are not enabled on this server, so a weekly run cannot start. "
                            "Start the server with NURSESYNC_LIVE=1.", 503)
        return run_manager.start(body.unit, body.week_start, body.case_id)

    @app.get("/api/runs/{run_id}", response_model=RunStatus)
    def get_run(run_id: str) -> Any:
        found = run_manager.status(run_id) if run_manager is not None else None
        if found is None:
            return _message(f"No run {run_id} was started in this server session.", 404)
        return found

    @app.get("/api/cases", response_model=CaseList)
    def list_cases() -> CaseList:
        found: List[CaseSummary] = []
        broken: List[Dict[str, str]] = []
        for case_id in store.list_ids():
            try:
                c = store.load(case_id)
            except CaseStoreError as err:
                broken.append({"case_id": case_id, "error": str(err)})
                continue
            found.append(CaseSummary(case_id=c.case_id, status=c.status, outcome=c.outcome, unit=c.unit,
                                     week_start=c.week_start, start_time=c.start_time, trigger=c.trigger,
                                     parent_case_id=c.parent_case_id, newer_case_id=c.newer_case_id))
        found.sort(key=lambda s: s.start_time, reverse=True)
        return CaseList(cases=found, unreadable=broken)

    @app.get("/api/cases/{case_id}", response_model=CaseRecord)
    def get_case(case_id: str) -> CaseRecord:
        return store.load(case_id)

    @app.post("/api/cases/{case_id}/approve", response_model=CaseRecord)
    def approve_case(case_id: str, body: Optional[ApproveBody] = None) -> CaseRecord:
        acknowledge = body.acknowledge_open_issues if body is not None else False
        with one_at_a_time(case_id):
            return store.update(case_id, lambda r: approve(r, acknowledge))

    @app.post("/api/cases/{case_id}/reject", response_model=CaseRecord)
    def reject_case(case_id: str) -> CaseRecord:
        with one_at_a_time(case_id):
            return store.update(case_id, reject)

    @app.post("/api/cases/{case_id}/change-demand", response_model=ChangeDemandResult)
    def change_case_demand(case_id: str, body: ChangeDemandBody) -> Any:
        if not live:
            return _message("Live agents are not enabled on this server, so a demand change cannot rerun the "
                            "Scheduler. Start the server with NURSESYNC_LIVE=1.", 503)
        with one_at_a_time(case_id):
            record = store.load(case_id)
            new_id = body.new_case_id or f"case-{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
            if store.exists(new_id):
                raise DecisionRefused(f"A case with id {new_id} already exists.")
            check_demand_changes(record, body.changes)  # refuse a bad request BEFORE it spends anything
            if usage is not None:
                usage.try_spend("change_demand", case_id)
            inputs = load_roster_and_rules()
            old, child = change_demand(record, body.changes, new_id, scheduler_factory, rules_checker,
                                       inputs.roster, inputs.rules, store=store)
            return ChangeDemandResult(old=old, child=child)

    @app.post("/api/cases/{case_id}/call-out", response_model=ChangeDemandResult)
    def call_out_case(case_id: str, body: CallOutBody) -> Any:
        if not live:
            return _message("Live agents are not enabled on this server, so a call-out cannot rerun the "
                            "Scheduler. Start the server with NURSESYNC_LIVE=1.", 503)
        now = datetime.now().isoformat(timespec="seconds")
        callouts = [Callout(nurse_id=c.nurse_id, date=c.date, shift=c.shift, reported_at=c.reported_at or now)
                    for c in body.call_outs]
        with one_at_a_time(case_id):
            record = store.load(case_id)
            new_id = body.new_case_id or f"case-{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
            if store.exists(new_id):
                raise DecisionRefused(f"A case with id {new_id} already exists.")
            inputs = load_roster_and_rules()
            check_call_outs(record, callouts, inputs.roster)  # refuse a bad request BEFORE it spends anything
            if usage is not None:
                usage.try_spend("call_out", case_id)
            old, child = run_call_out(record, callouts, new_id, scheduler_factory, rules_checker,
                                      inputs.roster, inputs.rules, store=store)
            return ChangeDemandResult(old=old, child=child)

    return app
