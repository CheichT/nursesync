"""The live Demand and Availability agents, tested with fake clients (no API calls), then through the orchestrator."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.availability.agent import AnthropicAvailabilityAgent
from app.agents.data_source import MockSource
from app.agents.demand.agent import AnthropicDemandAgent, rows_from_reply
from app.contract.models import Draft
from app.harness.phase1 import load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler
from app.orchestrator import make_snapshot, run_case, snapshot_id_for

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"
REFERENCE = json.loads((MOCK / "reference_draft.json").read_text())


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input={})


class FakeClient:
    def __init__(self, replies, stop_reason="end_turn"):
        self.replies, self.requests, self.messages, self.stop_reason = list(replies), [], self, stop_reason

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return SimpleNamespace(content=self.replies.pop(0), stop_reason=self.stop_reason)


def snapshot():
    inputs = load_inputs(MOCK)
    return make_snapshot(inputs.roster, inputs.rules, "7W", "2026-11-02", "snap-case-1")


def demand_reply():
    rows = [{**{k: r[k] for k in ("unit", "date", "shift", "patient_count", "nurses_needed")}, "note": ""}
            for r in json.loads((MOCK / "demand.json").read_text())]
    return json.dumps({"rows": rows, "unusual": [], "needs_manual_review": []})


def availability_reply():
    rows = [{**{k: r[k] for k in ("nurse_id", "date", "shift", "available", "reason")}, "note": ""}
            for r in json.loads((MOCK / "availability.json").read_text())]
    return json.dumps({"rows": rows, "needs_manual_review": []})


def test_demand_agent_calls_its_tool_then_returns_rows_without_notes():
    client = FakeClient([[tool_use("t1", "get_demand")], [text(demand_reply())]])
    agent = AnthropicDemandAgent(client=client, source=MockSource(MOCK))
    rows = agent.run(snapshot()).rows
    assert len(rows) == 14 and all("note" not in r and "flag" not in r for r in rows)
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and "nurses_needed" not in tool_result["content"]  # counts only
    assert "Demand agent" in client.requests[0]["system"]
    sent = json.loads(client.requests[0]["messages"][0]["content"])
    assert sent["rules"] == {"ratio_patients_per_nurse": 5} and sent["unit"] == "7W"


def test_a_note_becomes_a_flag_and_status_is_stripped():
    rows = rows_from_reply({"rows": [{"unit": "7W", "note": "far busier night", "status": "ok"}]})
    assert rows == [{"unit": "7W", "flag": "far busier night"}]


def test_bad_replies_are_errors_not_answers():
    with pytest.raises(ValueError):
        AnthropicDemandAgent(client=FakeClient([[text("I could not do it")]]), source=MockSource(MOCK)).run(snapshot())
    with pytest.raises(ValueError):
        AnthropicDemandAgent(client=FakeClient([[text('{"rows": "none"}')]]), source=MockSource(MOCK)).run(snapshot())
    with pytest.raises(RuntimeError, match="cut off"):
        AnthropicDemandAgent(client=FakeClient([[text('{"rows": [')]], stop_reason="max_tokens"),
                             source=MockSource(MOCK)).run(snapshot())


def test_a_failing_data_source_is_reported_to_the_agent_not_hidden():
    class Broken:
        def get_demand(self, snapshot):
            raise RuntimeError("Shift Board is down")

    client = FakeClient([[tool_use("t1", "get_demand")], [text(demand_reply())]])
    AnthropicDemandAgent(client=client, source=Broken()).run(snapshot())
    assert "Shift Board is down" in client.requests[1]["messages"][-1]["content"][0]["content"]


def test_availability_agent_sends_the_roster_and_returns_rows():
    client = FakeClient([[tool_use("t1", "get_availability")], [text(availability_reply())]])
    rows = AnthropicAvailabilityAgent(client=client, source=MockSource(MOCK)).run(snapshot()).rows
    assert len(rows) == 336
    sent = json.loads(client.requests[0]["messages"][0]["content"])
    assert len(sent["roster"]) == 24 and "Availability agent" in client.requests[0]["system"]


def test_tool_loop_gives_up_after_too_many_turns():
    client = FakeClient([[tool_use(f"t{i}", "get_demand")] for i in range(20)])
    with pytest.raises(RuntimeError, match="tool turns"):
        AnthropicDemandAgent(client=client, source=MockSource(MOCK)).run(snapshot())


def test_both_live_agents_through_the_orchestrator_give_a_clean_case():
    inputs = load_inputs(MOCK)
    demand = AnthropicDemandAgent(client=FakeClient([[text(demand_reply())]]), source=MockSource(MOCK))
    availability = AnthropicAvailabilityAgent(client=FakeClient([[text(availability_reply())]]),
                                              source=MockSource(MOCK))
    rec = run_case(demand, availability,
                   ScriptedScheduler([Draft(**REFERENCE)], snapshot_id=snapshot_id_for("case-1")),
                   HintingRulesChecker(), inputs.roster, inputs.rules, "7W", "2026-11-02", "case-1")
    assert (rec.status, rec.outcome) == ("waiting_approval", "passed")
    assert rec.demand_result.counts.ok == 14 and rec.availability_result.counts.ok == 336


def test_an_agent_that_fails_leaves_its_rows_missing_in_the_orchestrator():
    inputs = load_inputs(MOCK)
    demand = AnthropicDemandAgent(client=FakeClient([[text("nope")]]), source=MockSource(MOCK))
    availability = AnthropicAvailabilityAgent(client=FakeClient([[text(availability_reply())]]),
                                              source=MockSource(MOCK))
    rec = run_case(demand, availability, ScriptedScheduler([Draft(**REFERENCE)]), HintingRulesChecker(),
                   inputs.roster, inputs.rules, "7W", "2026-11-02", "case-1")
    assert rec.demand_result.counts.missing == 14
