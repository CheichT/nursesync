"""Starting a weekly run from the API, the one-at-a-time rule, and the daily cap on paid operations.
Scripted agents only: no API calls, no cost."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import serve
from app.api import create_app
from app.case_store import CaseStore
from app.contract.models import Draft
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedAvailabilityAgent, ScriptedDemandAgent, ScriptedScheduler
from app.orchestrator import building_record, make_snapshot
from app.runs import RunManager, sweep_stale
from app.sample_cases import REFERENCE
from app.usage import SpendCapReached, UsageMeter, max_from_env

LOCAL = "http://127.0.0.1:8000"
WEEK = "2026-11-02"
BODY = {"unit": "7W", "week_start": WEEK}
CHANGE = {"changes": [{"unit": "7W", "date": "2026-11-03", "shift": "night", "nurses_needed": 4}]}


def raw(name):
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def scripted_scheduler(case_id, snapshot_id):
    return ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id)


def manager(store, usage=None, demand=None, clock=None):
    return RunManager(store, demand or (lambda: ScriptedDemandAgent(raw("demand.json"))),
                      lambda: ScriptedAvailabilityAgent(raw("availability.json")), scripted_scheduler,
                      HintingRulesChecker(), usage=usage, clock=clock)


def build(tmp_path, max_per_day=10, demand=None, with_runs=True):
    store = CaseStore(tmp_path / "cases")
    serve.seed_samples(store)
    usage = UsageMeter(tmp_path / "usage.json", max_per_day)
    runs = manager(store, usage, demand) if with_runs else None
    app = create_app(store, scripted_scheduler, HintingRulesChecker(), run_manager=runs, usage=usage)
    return store, usage, runs, TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


# --- starting a run ----------------------------------------------------------------------------------------------


def test_a_weekly_run_starts_in_the_background_and_ends_waiting_for_the_manager(tmp_path):
    store, usage, runs, c = build(tmp_path)
    started = c.post("/api/runs", json={**BODY, "case_id": "run-a"})
    assert started.status_code == 202 and started.json()["state"] in ("running", "done")
    assert started.json()["case_id"] == "run-a" and runs.wait("run-a")
    done = c.get("/api/runs/run-a").json()
    assert (done["state"], done["outcome"], done["message"]) == ("done", "passed", "") and done["finished_at"]
    case = store.load("run-a")
    assert (case.status, case.outcome, case.trigger, case.unit) == ("waiting_approval", "passed", "weekly", "7W")
    assert "run-a" in [s["case_id"] for s in c.get("/api/cases").json()["cases"]]


def test_a_run_without_a_case_id_makes_one(tmp_path):
    store, usage, runs, c = build(tmp_path)
    made = c.post("/api/runs", json=BODY).json()
    assert made["case_id"].startswith("run-7W-2026-11-02-") and runs.wait(made["case_id"]) and store.exists(made["case_id"])


def test_starting_a_run_is_off_without_live_agents_and_spends_nothing(tmp_path):
    store, usage, runs, c = build(tmp_path, with_runs=False)
    off = c.post("/api/runs", json=BODY)
    assert off.status_code == 503 and "NURSESYNC_LIVE=1" in off.json()["message"] and usage.snapshot()["used_today"] == 0


def test_the_guards_cover_starting_a_run(tmp_path):
    store, usage, runs, c = build(tmp_path)
    assert c.post("/api/runs", json=BODY, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/runs", content=json.dumps(BODY).encode()).status_code == 415
    rebound = TestClient(c.app, base_url="http://evil.example:8000", raise_server_exceptions=False)
    assert rebound.post("/api/runs", json=BODY).status_code == 400
    assert usage.snapshot()["used_today"] == 0 and runs.active_ids() == []  # nothing started, nothing counted


def test_bad_requests_are_refused_without_spending_anything(tmp_path):
    store, usage, runs, c = build(tmp_path)
    cases = [({"unit": "9E", "week_start": WEEK}, 422, "Unknown unit"),
             ({"unit": "7W", "week_start": "2026-11-03"}, 422, "not a Monday"),
             ({"unit": "7W", "week_start": "2026-11-09"}, 422, "no data for the week"),
             ({"unit": "7W", "week_start": "next week"}, 422, "must be a date"),
             ({**BODY, "case_id": "bad id!"}, 422, "not a valid case id"),
             ({**BODY, "case_id": "demo-passed"}, 409, "already exists"),
             ({**BODY, "extra": 1}, 422, "")]
    for body, status, text in cases:
        r = c.post("/api/runs", json=body)
        assert r.status_code == status and text in r.text, body
    assert usage.snapshot()["used_today"] == 0 and runs.active_ids() == []


def test_only_one_run_at_a_time_and_a_refused_second_one_costs_nothing(tmp_path):
    started, release = threading.Event(), threading.Event()

    def slow_demand():
        started.set()
        release.wait(10)
        return ScriptedDemandAgent(raw("demand.json"))

    store, usage, runs, c = build(tmp_path, demand=slow_demand)
    assert c.post("/api/runs", json={**BODY, "case_id": "first"}).status_code == 202
    assert started.wait(10)
    busy = c.post("/api/runs", json={**BODY, "case_id": "second"})
    assert busy.status_code == 409 and "already in progress" in busy.json()["message"]
    assert usage.snapshot()["used_today"] == 1 and not store.exists("second")
    assert c.get("/api/runs/first").json()["state"] == "running"
    release.set()
    assert runs.wait("first")
    assert c.post("/api/runs", json={**BODY, "case_id": "third"}).status_code == 202  # the slot is free again
    assert runs.wait("third")


def test_a_failed_run_says_so_leaves_no_case_and_frees_the_slot(tmp_path):
    def broken():
        raise RuntimeError("secret path /Users/x and a key")

    store, usage, runs, c = build(tmp_path, demand=broken)
    assert c.post("/api/runs", json={**BODY, "case_id": "doomed"}).status_code == 202 and runs.wait("doomed")
    status = c.get("/api/runs/doomed").json()
    assert status["state"] == "failed" and "secret" not in json.dumps(status) and "no case was saved" in status["message"]
    assert not store.exists("doomed") and usage.snapshot()["used_today"] == 1  # the money may be spent, so it counts
    runs._make_demand = lambda: ScriptedDemandAgent(raw("demand.json"))
    assert c.post("/api/runs", json={**BODY, "case_id": "retry"}).status_code == 202 and runs.wait("retry")


def test_unknown_runs_are_404_and_a_new_server_forgets_old_runs(tmp_path):
    store, usage, runs, c = build(tmp_path)
    assert c.get("/api/runs/nope").status_code == 404
    c.post("/api/runs", json={**BODY, "case_id": "r1"})
    assert runs.wait("r1")
    fresh = manager(store, usage)
    assert fresh.status("r1") is None  # run status is not saved; the case itself is


# --- the daily cap ------------------------------------------------------------------------------------------------


def test_the_daily_cap_stops_paid_runs_before_they_spend(tmp_path):
    store, usage, runs, c = build(tmp_path, max_per_day=2)
    for name in ("a", "b"):
        assert c.post("/api/runs", json={**BODY, "case_id": name}).status_code == 202 and runs.wait(name)
    over = c.post("/api/runs", json={**BODY, "case_id": "c"})
    assert over.status_code == 429 and "daily limit of 2" in over.json()["message"] and not store.exists("c")
    assert c.get("/api/usage").json() == {"capped": True, "used_today": 2, "max_per_day": 2, "remaining": 0,
                                           "date": usage.snapshot()["date"]}


def test_the_count_survives_a_restart_and_a_new_day_starts_at_zero(tmp_path):
    path = tmp_path / "usage.json"
    day = [datetime(2026, 11, 2, 9, 0)]
    meter = UsageMeter(path, 3, clock=lambda: day[0])
    meter.try_spend("weekly_run", "x")
    meter.try_spend("change_demand", "y")
    again = UsageMeter(path, 3, clock=lambda: day[0])  # a "restart"
    assert again.snapshot()["used_today"] == 2 and again.snapshot()["remaining"] == 1
    day[0] += timedelta(days=1)
    assert again.snapshot()["used_today"] == 0
    again.try_spend("weekly_run", "z")
    assert json.loads(path.read_text())["date"] == "2026-11-03"


def test_change_demand_is_counted_too_and_a_bad_one_is_not(tmp_path):
    store, usage, runs, c = build(tmp_path, max_per_day=1)
    bad = {"changes": [{"unit": "7W", "date": "2027-01-01", "shift": "day", "nurses_needed": 4}]}
    assert c.post("/api/cases/demo-demand-change/change-demand", json=bad).status_code == 409
    assert usage.snapshot()["used_today"] == 0  # refused before it could spend
    ok = c.post("/api/cases/demo-demand-change/change-demand", json={**CHANGE, "new_case_id": "child-1"})
    assert ok.status_code == 200 and usage.snapshot()["used_today"] == 1
    capped = c.post("/api/cases/demo-needs-review/change-demand", json={**CHANGE, "new_case_id": "child-2"})
    assert capped.status_code == 429 and not store.exists("child-2")
    assert store.load("demo-needs-review").status == "waiting_approval"


def test_the_cap_cannot_be_beaten_by_many_requests_at_once(tmp_path):
    meter = UsageMeter(tmp_path / "usage.json", 5)
    results, gate = [], threading.Barrier(12)

    def spend():
        gate.wait()
        try:
            meter.try_spend("weekly_run", "x")
            results.append(True)
        except SpendCapReached:
            results.append(False)

    threads = [threading.Thread(target=spend) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 5 and meter.snapshot()["used_today"] == 5


def test_an_unreadable_usage_file_stops_paid_runs_instead_of_guessing(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("{not json")
    meter = UsageMeter(path, 10)
    with pytest.raises(SpendCapReached, match="cannot be read"):
        meter.try_spend("weekly_run", "x")
    path.write_text(json.dumps({"date": "2026-11-02", "events": "oops"}))
    with pytest.raises(SpendCapReached, match="cannot be read"):
        meter.try_spend("weekly_run", "x")


def test_a_cap_of_zero_refuses_everything_and_the_env_setting_is_read_safely(tmp_path, monkeypatch):
    with pytest.raises(SpendCapReached, match="daily limit of 0"):
        UsageMeter(tmp_path / "u.json", 0).try_spend("weekly_run")
    for value, expected in (("4", 4), ("0", 0), ("", 10), ("lots", 10), ("-3", 10), ("2.5", 10)):
        monkeypatch.setenv("NURSESYNC_MAX_PAID_OPS_PER_DAY", value)
        assert max_from_env() == expected, value
    monkeypatch.delenv("NURSESYNC_MAX_PAID_OPS_PER_DAY")
    assert max_from_env() == 10


def test_without_a_cap_the_usage_endpoint_says_so(tmp_path):
    store = CaseStore(tmp_path)
    c = TestClient(create_app(store), base_url=LOCAL)
    assert c.get("/api/usage").json() == {"capped": False, "used_today": 0, "max_per_day": None, "remaining": None, "date": None}


# --- stale cases --------------------------------------------------------------------------------------------------


def test_a_building_case_left_by_a_crash_is_swept_but_recent_and_running_ones_are_kept(tmp_path):
    store = CaseStore(tmp_path)
    inputs = load_inputs()
    now = datetime(2026, 11, 2, 12, 0)

    def building(case_id, minutes_ago):
        snap = make_snapshot(inputs.roster, inputs.rules, "7W", WEEK, f"snap-{case_id}",
                             now=lambda: now - timedelta(minutes=minutes_ago))
        store.save(building_record(snap, case_id))

    building("old-crash", 90)
    building("recent", 5)
    building("still-running", 90)
    serve.seed_samples(store)
    removed = sweep_stale(store, active_ids=["still-running"], now=now)
    assert removed == 1 and not store.exists("old-crash")
    assert store.exists("recent") and store.exists("still-running") and store.exists("demo-passed")


# --- serve.py ------------------------------------------------------------------------------------------------------------


def test_the_server_wires_a_cap_and_runs_only_when_live_agents_are_on(tmp_path, monkeypatch):
    off = TestClient(serve.build_app(tmp_path / "a", live=False), base_url=LOCAL)
    assert off.post("/api/runs", json=BODY).status_code == 503 and off.get("/api/usage").json()["capped"] is False
    monkeypatch.setattr("app.config.load_api_key", lambda: "test-key-not-real")
    monkeypatch.setattr("app.agents.common.load_api_key", lambda: "test-key-not-real")  # the clients read it here
    on = TestClient(serve.build_app(tmp_path / "b", live=True, usage_path=tmp_path / "usage.json"), base_url=LOCAL)
    usage = on.get("/api/usage").json()
    assert usage["capped"] is True and usage["used_today"] == 0 and usage["max_per_day"] == 10
    assert on.get("/api/health").json()["live_agents"] is True
