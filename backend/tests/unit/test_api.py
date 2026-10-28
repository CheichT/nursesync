"""The local case API, with a temporary case store and scripted agents (no API calls, no cost)."""

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import serve
from app.api import create_app
from app.case_store import CaseStore
from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler
from app.sample_cases import OUT_DIR, REFERENCE

CHANGE = {"changes": [{"unit": "7W", "date": "2026-11-03", "shift": "night", "nurses_needed": 4}]}


@pytest.fixture()
def store(tmp_path):
    s = CaseStore(tmp_path)
    serve.seed_samples(s)  # the undecided version of each sample case: 8 case ids
    return s


def scripted(case_id, snapshot_id):
    return ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id)


LOCAL = "http://127.0.0.1:8000"  # the Host header the real server sees; the default "testserver" is not allowed


def local_client(app):
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


@pytest.fixture()
def client(store):
    return local_client(create_app(store))


@pytest.fixture()
def live_client(store):
    return local_client(create_app(store, scripted, HintingRulesChecker()))


# --- reading ------------------------------------------------------------------------------------


def test_health_says_whether_live_agents_are_on(client, live_client):
    assert client.get("/api/health").json() == {"ok": True, "live_agents": False}
    assert live_client.get("/api/health").json() == {"ok": True, "live_agents": True}


def test_list_cases_returns_newest_first_summaries_without_the_big_fields(client):
    body = client.get("/api/cases").json()
    assert len(body["cases"]) == 8 and body["unreadable"] == []
    first = body["cases"][0]
    assert set(first) == {"case_id", "status", "outcome", "unit", "week_start", "start_time", "trigger",
                          "parent_case_id", "newer_case_id"}
    times = [c["start_time"] for c in body["cases"]]
    assert times == sorted(times, reverse=True)


def test_get_case_returns_exactly_the_sample_file(client):
    matched = 0
    for path in sorted(Path(OUT_DIR).glob("*.json")):
        wanted = json.loads(path.read_text())
        got = client.get(f"/api/cases/{wanted['case_id']}").json()
        if got["status"] == wanted["status"]:  # the seeded version of that case
            assert got == wanted
            matched += 1
    assert matched == 8


def test_unknown_and_invalid_ids(client):
    missing = client.get("/api/cases/nope")
    assert missing.status_code == 404 and "no saved case" in missing.json()["message"]
    bad = client.get("/api/cases/a.b")
    assert bad.status_code == 422 and "not a valid case id" in bad.json()["message"]


def test_an_unreadable_file_is_reported_not_hidden(store, client):
    (store.folder / "broken.json").write_text("{not json")
    body = client.get("/api/cases").json()
    assert len(body["cases"]) == 8 and body["unreadable"][0]["case_id"] == "broken"


# --- approve and reject -----------------------------------------------------------------------------


def test_approve_saves_the_decision_and_a_second_approve_is_refused(client, store):
    done = client.post("/api/cases/demo-passed/approve", json={})
    assert done.status_code == 200 and done.json()["status"] == "approved"
    assert done.json()["manager_decision"] == "approved" and done.json()["decision_time"]
    assert store.load("demo-passed").status == "approved"  # saved to disk
    again = client.post("/api/cases/demo-passed/approve", json={})
    assert again.status_code == 409 and "already approved" in again.json()["message"]


def test_open_issues_need_the_acknowledgement(client, store):
    refused = client.post("/api/cases/demo-open-issues/approve", json={})
    assert refused.status_code == 409 and "open issues" in refused.json()["message"]
    assert store.load("demo-open-issues").status == "waiting_approval"  # nothing saved
    ok = client.post("/api/cases/demo-open-issues/approve", json={"acknowledge_open_issues": True})
    assert ok.status_code == 200 and ok.json()["decision_details"]["acknowledged_open_issues"] is True


def test_out_of_date_and_stopped_cases_cannot_be_approved(client):
    stale = client.post("/api/cases/demo-call-out/approve", json={})
    assert stale.status_code == 409 and "out of date" in stale.json()["message"] and "demo-call-out-2" in stale.json()["message"]
    stopped = client.post("/api/cases/demo-stopped-missing-input/approve", json={})
    assert stopped.status_code == 409 and "required input is missing" in stopped.json()["message"]


def test_reject_ends_the_case_with_outcome_rejected(client, store):
    done = client.post("/api/cases/demo-stopped-missing-input/reject", json={})
    assert done.status_code == 200 and (done.json()["status"], done.json()["outcome"]) == ("rejected", "rejected")
    assert store.load("demo-stopped-missing-input").outcome == "rejected"
    assert client.post("/api/cases/demo-stopped-missing-input/reject", json={}).status_code == 409


def test_two_clicks_at_once_cannot_both_approve(client):
    results = []
    gate = threading.Barrier(6)

    def click():
        gate.wait()
        results.append(client.post("/api/cases/demo-passed/approve", json={}).status_code)

    threads = [threading.Thread(target=click) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 409, 409, 409, 409, 409]


# --- change demand ------------------------------------------------------------------------------------


def test_change_demand_is_off_without_live_agents_and_changes_nothing(client, store):
    off = client.post("/api/cases/demo-demand-change/change-demand", json=CHANGE)
    assert off.status_code == 503 and "NURSESYNC_LIVE=1" in off.json()["message"]
    assert store.load("demo-demand-change").status == "waiting_approval"


def test_change_demand_starts_a_child_case_and_retires_the_old_one(live_client, store):
    before = set(store.list_ids())
    done = live_client.post("/api/cases/demo-demand-change/change-demand", json={**CHANGE, "new_case_id": "demo-child-x"})
    assert done.status_code == 200
    old, child = done.json()["old"], done.json()["child"]
    assert (old["status"], old["newer_case_id"], old["decision_details"]["action"]) == ("out_of_date", "demo-child-x", "change_demand")
    assert (child["case_id"], child["parent_case_id"], child["status"]) == ("demo-child-x", "demo-demand-change", "waiting_approval")
    assert set(store.list_ids()) == before | {"demo-child-x"}
    assert store.load("demo-demand-change").status == "out_of_date" and store.load("demo-child-x").model_dump(mode="json") == child


def test_change_demand_makes_its_own_id_when_none_is_given(live_client, store):
    done = live_client.post("/api/cases/demo-demand-change/change-demand", json=CHANGE)
    child_id = done.json()["child"]["case_id"]
    assert child_id.startswith("case-") and store.exists(child_id)


def test_change_demand_refusals(live_client, store):
    assert live_client.post("/api/cases/no-such-case/change-demand", json=CHANGE).status_code == 404
    decided = live_client.post("/api/cases/demo-passed/approve", json={})
    assert decided.status_code == 200
    again = live_client.post("/api/cases/demo-passed/change-demand", json=CHANGE)
    assert again.status_code == 409 and "already approved" in again.json()["message"]
    unknown_row = {"changes": [{"unit": "7W", "date": "2027-01-01", "shift": "day", "nurses_needed": 4}]}
    assert "no demand row" in live_client.post("/api/cases/demo-needs-review/change-demand", json=unknown_row).json()["message"]
    assert live_client.post("/api/cases/demo-needs-review/change-demand", json={"changes": []}).status_code == 422
    taken = live_client.post("/api/cases/demo-needs-review/change-demand", json={**CHANGE, "new_case_id": "demo-passed"})
    assert taken.status_code == 409 and "already exists" in taken.json()["message"]
    assert store.load("demo-needs-review").status == "waiting_approval"


# --- bad input, errors, and the safety settings ----------------------------------------------------------------


def test_request_bodies_are_strict(client, live_client):
    assert client.post("/api/cases/demo-passed/approve", json={"acknowledge_open_issues": True, "extra": 1}).status_code == 422
    assert client.post("/api/cases/demo-passed/approve", json={"acknowledge_open_issues": "maybe"}).status_code == 422
    assert client.post("/api/cases/demo-passed/approve", content="not json",
                       headers={"Content-Type": "application/json"}).status_code == 422
    bad = {"changes": [{"unit": "7W", "date": "2026-11-03", "shift": "night", "nurses_needed": -1}]}
    assert live_client.post("/api/cases/demo-passed/change-demand", json=bad).status_code == 422


def test_an_unexpected_error_is_a_generic_500_with_no_details(store, monkeypatch):
    c = local_client(create_app(store))
    monkeypatch.setattr(CaseStore, "load", lambda self, cid: (_ for _ in ()).throw(RuntimeError("secret path /Users/x")))
    r = c.get("/api/cases/demo-passed")
    assert r.status_code == 500 and "secret" not in r.text and "Users" not in r.text and "Nothing was changed" in r.json()["message"]


def test_only_the_local_dev_origin_is_allowed_by_cors(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_only_get_and_post_exist_and_no_delete_or_put(client):
    assert client.delete("/api/cases/demo-passed").status_code == 405
    assert client.put("/api/cases/demo-passed").status_code == 405


# --- serve.py -----------------------------------------------------------------------------------------------------


def test_seed_samples_adds_the_samples_once(tmp_path):
    empty = CaseStore(tmp_path)
    assert serve.seed_samples(empty) == 8 and len(empty.list_ids()) == 8
    assert empty.load("demo-passed").status == "waiting_approval"  # not the approved version
    assert empty.load("demo-demand-change").status == "waiting_approval"
    assert serve.seed_samples(empty) == 0  # nothing added twice
    empty.update("demo-passed", lambda r: __import__("app.decisions", fromlist=["approve"]).approve(r))
    assert serve.seed_samples(empty) == 0 and empty.load("demo-passed").status == "approved"  # a decision is kept


def test_the_server_listens_on_this_computer_only(tmp_path, monkeypatch):
    seen = {}
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    assert serve.main(["--port", "8123", "--store-dir", str(tmp_path)]) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8123
    with pytest.raises(SystemExit):  # there is no option to expose it
        serve.main(["--host", "0.0.0.0"])


def test_live_agents_stay_off_unless_asked(tmp_path, monkeypatch):
    monkeypatch.delenv("NURSESYNC_LIVE", raising=False)
    off = TestClient(serve.build_app(tmp_path), base_url=LOCAL)
    assert off.get("/api/health").json()["live_agents"] is False
    monkeypatch.setenv("NURSESYNC_LIVE", "1")
    monkeypatch.setattr("app.config.load_api_key", lambda: "test-key-not-real")
    monkeypatch.setattr("app.agents.common.load_api_key", lambda: "test-key-not-real")  # the clients read it here
    on = TestClient(serve.build_app(tmp_path), base_url=LOCAL)
    assert on.get("/api/health").json()["live_agents"] is True


# --- the guards: web pages in the browser must not be able to drive this API -------------------------------------------


EVIL = {"Origin": "https://evil.example"}


def test_a_post_from_another_web_page_is_refused_and_changes_nothing(client, store):
    assert client.post("/api/cases/demo-needs-review/reject", json={}, headers=EVIL).status_code == 403
    assert client.post("/api/cases/demo-open-issues/approve", json={"acknowledge_open_issues": True},
                       headers=EVIL).status_code == 403
    assert client.post("/api/cases/demo-open-issues/approve", json={}, headers={"Origin": "null"}).status_code == 403
    assert store.load("demo-needs-review").status == "waiting_approval"
    assert store.load("demo-open-issues").status == "waiting_approval"


def test_the_local_dev_origin_may_post(client):
    ok = client.post("/api/cases/demo-passed/approve", json={}, headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 200


def test_a_post_without_a_json_content_type_is_refused(client, store):
    # the cross-site trick that skips CORS: a JSON body sent with no Content-Type, or as text/plain
    body = json.dumps({"acknowledge_open_issues": True}).encode()
    assert client.post("/api/cases/demo-open-issues/approve", content=body).status_code == 415
    assert client.post("/api/cases/demo-open-issues/approve", content=body,
                       headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/cases/demo-needs-review/reject").status_code == 415  # even with no body
    assert store.load("demo-open-issues").status == "waiting_approval"
    assert store.load("demo-needs-review").status == "waiting_approval"


def test_a_request_for_another_host_name_is_refused(store):
    app = create_app(store)
    rebound = TestClient(app, base_url="http://evil.example:8000", raise_server_exceptions=False)
    assert rebound.get("/api/cases").status_code == 400
    assert rebound.post("/api/cases/demo-passed/approve", json={}).status_code == 400
    assert local_client(app).get("/api/cases").status_code == 200
    assert TestClient(app, base_url="http://localhost:8000").get("/api/health").status_code == 200


# --- no ghost cases, per-case locking, optional approve body --------------------------------------------------------------


def test_a_failed_change_demand_leaves_no_ghost_case_and_can_be_retried(store):
    def broken(case_id, snapshot_id):
        raise RuntimeError("no API key")

    c = local_client(create_app(store, broken, HintingRulesChecker()))
    failed = c.post("/api/cases/demo-demand-change/change-demand", json={**CHANGE, "new_case_id": "retry-me"})
    assert failed.status_code == 500 and "Nothing was changed" in failed.json()["message"]
    assert not store.exists("retry-me") and store.load("demo-demand-change").status == "waiting_approval"
    fixed = local_client(create_app(store, scripted, HintingRulesChecker()))
    assert fixed.post("/api/cases/demo-demand-change/change-demand", json={**CHANGE, "new_case_id": "retry-me"}).status_code == 200


def test_a_failure_while_saving_the_finished_case_leaves_no_ghost_case_either(store, monkeypatch):
    real_save = CaseStore.save

    def flaky_save(self, record):
        if record.case_id == "ghost" and record.status != "building":
            raise OSError("disk full")  # the first save (building) worked, the final one fails
        return real_save(self, record)

    monkeypatch.setattr(CaseStore, "save", flaky_save)
    c = local_client(create_app(store, scripted, HintingRulesChecker()))
    failed = c.post("/api/cases/demo-demand-change/change-demand", json={**CHANGE, "new_case_id": "ghost"})
    assert failed.status_code == 500 and "disk full" not in failed.text
    assert not store.exists("ghost") and store.load("demo-demand-change").status == "waiting_approval"


def test_discard_building_only_removes_a_case_that_never_finished(tmp_path):
    s = CaseStore(tmp_path)
    serve.seed_samples(s)
    assert s.discard_building("demo-passed") is False and s.exists("demo-passed")  # waiting_approval: untouched
    assert s.discard_building("no-such-case") is False


def test_a_busy_case_refuses_a_second_request_at_once_but_other_cases_are_not_blocked(store):
    started, release = threading.Event(), threading.Event()

    def slow(case_id, snapshot_id):
        started.set()
        release.wait(10)  # holds the case, like a live Scheduler run
        return ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id)

    c = local_client(create_app(store, slow, HintingRulesChecker()))
    first = {}
    worker = threading.Thread(target=lambda: first.update(
        r=c.post("/api/cases/demo-demand-change/change-demand", json={**CHANGE, "new_case_id": "slow-child"})))
    worker.start()
    assert started.wait(10)
    busy = c.post("/api/cases/demo-demand-change/reject", json={})  # the same case: refused at once, not queued
    assert busy.status_code == 409 and "already changing this case" in busy.json()["message"]
    assert c.post("/api/cases/demo-passed/approve", json={}).status_code == 200  # a different case is not blocked
    release.set()
    worker.join(30)
    assert first["r"].status_code == 200


def test_approve_needs_no_body_at_all(client):
    done = client.post("/api/cases/demo-passed/approve", headers={"Content-Type": "application/json"})
    assert done.status_code == 200 and done.json()["decision_details"]["acknowledged_open_issues"] is False
    refused = client.post("/api/cases/demo-open-issues/approve", headers={"Content-Type": "application/json"})
    assert refused.status_code == 409 and "open issues" in refused.json()["message"]
