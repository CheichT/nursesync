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


@pytest.fixture()
def client(store):
    return TestClient(create_app(store), raise_server_exceptions=False)


@pytest.fixture()
def live_client(store):
    return TestClient(create_app(store, scripted, HintingRulesChecker()), raise_server_exceptions=False)


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
    done = client.post("/api/cases/demo-stopped-missing-input/reject")
    assert done.status_code == 200 and (done.json()["status"], done.json()["outcome"]) == ("rejected", "rejected")
    assert store.load("demo-stopped-missing-input").outcome == "rejected"
    assert client.post("/api/cases/demo-stopped-missing-input/reject").status_code == 409


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


def test_request_bodies_are_strict(client):
    assert client.post("/api/cases/demo-passed/approve", json={"acknowledge_open_issues": True, "extra": 1}).status_code == 422
    assert client.post("/api/cases/demo-passed/approve", json={"acknowledge_open_issues": "maybe"}).status_code == 422
    assert client.post("/api/cases/demo-passed/approve", content="not json",
                       headers={"Content-Type": "application/json"}).status_code == 422
    bad = {"changes": [{"unit": "7W", "date": "2026-11-03", "shift": "night", "nurses_needed": -1}]}
    assert client.post("/api/cases/demo-passed/change-demand", json=bad).status_code in (422, 503)


def test_an_unexpected_error_is_a_generic_500_with_no_details(store, monkeypatch):
    c = TestClient(create_app(store), raise_server_exceptions=False)
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


def test_the_server_listens_on_this_computer_only():
    assert serve.HOST == "127.0.0.1"
    assert "0.0.0.0" not in Path(serve.__file__).read_text().replace('"0.0.0.0" not', "")


def test_live_agents_stay_off_unless_asked(tmp_path, monkeypatch):
    monkeypatch.delenv("NURSESYNC_LIVE", raising=False)
    off = TestClient(serve.build_app(tmp_path))
    assert off.get("/api/health").json()["live_agents"] is False
    monkeypatch.setenv("NURSESYNC_LIVE", "1")
    monkeypatch.setattr("app.config.load_api_key", lambda: "test-key-not-real")
    on = TestClient(serve.build_app(tmp_path))
    assert on.get("/api/health").json()["live_agents"] is True
