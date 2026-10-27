"""Rules Checker, baseline and the eval runner, tested with fake clients (no API calls)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import run_eval
from app.agents.baseline.agent import run_baseline, run_tool, score
from app.agents.rules_checker.agent import AnthropicRulesChecker, build_message
from app.contract.models import Draft
from app.harness.phase1 import load_inputs, load_scenario, run_phase1
from app.harness.stand_ins import ScriptedScheduler, without

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"
REFERENCE = json.loads((MOCK / "reference_draft.json").read_text())


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, tool_input=None):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=tool_input or {})


class FakeClient:
    def __init__(self, replies):
        self.replies, self.requests, self.messages = list(replies), [], self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return SimpleNamespace(content=self.replies.pop(0), stop_reason="end_turn")


def violations_for(draft):
    inputs = load_inputs(MOCK)
    from app.harness.rules import check_rules
    return inputs, check_rules(draft, inputs.demand, inputs.availability, inputs.roster, inputs.rules).violations


def test_rules_checker_sends_only_hard_violations_and_returns_the_agents_list():
    broken = without(Draft(**REFERENCE), 3)
    inputs, found = violations_for(broken)
    hints = [v.model_copy(update={"fix_hint": "Add one nurse."}) for v in found]
    client = FakeClient([[text(json.dumps([h.model_dump(mode="json") for h in hints]))]])
    checker = AnthropicRulesChecker(client=client)
    out = checker.add_fix_hints(broken, found, inputs)
    sent = json.loads(client.requests[0]["messages"][0]["content"])
    assert set(sent) == {"violations", "draft", "roster", "rules", "availability"}
    assert all(v["severity"] == "hard" for v in sent["violations"])
    assert [v.fix_hint for v in out] == ["Add one nurse."] * len(found)
    assert "Rules Checker agent" in client.requests[0]["system"]


def test_rules_checker_reply_that_is_not_a_list_is_an_error_the_harness_survives():
    broken = without(Draft(**REFERENCE), 3)
    inputs, found = violations_for(broken)
    with pytest.raises(ValueError):
        AnthropicRulesChecker(client=FakeClient([[text("looks fine to me")]])).add_fix_hints(broken, found, inputs)
    scheduler = ScriptedScheduler([broken, REFERENCE])
    result = run_phase1(scheduler, AnthropicRulesChecker(client=FakeClient([[text("nope")]])), inputs)
    assert result.outcome == "passed" and "failed" in result.rounds[0].note


def test_build_message_skips_soft_violations():
    inputs, found = violations_for(Draft(**REFERENCE))
    soft = found[0:0]
    assert json.loads(build_message(Draft(**REFERENCE), soft, inputs))["violations"] == []


def test_baseline_uses_tools_and_is_scored_by_code_not_its_own_claim():
    inputs = load_inputs(MOCK)
    final = {"final_draft": REFERENCE, "check_rules_passed": False, "hard_violation_count": 99}
    client = FakeClient([
        [tool_use("t1", "get_demand"), tool_use("t2", "get_roster")],
        [tool_use("t3", "check_rules", {"draft": REFERENCE})],
        [text(json.dumps(final))],
    ])
    metrics = run_baseline(inputs, client=client)
    assert metrics["outcome"] == "passed" and metrics["hard_violation_count"] == 0
    assert metrics["fully_staffed_shifts"] == 14 and metrics["coverage_rate"] == 1.0
    assert metrics["self_report_matches"] is False  # it claimed failure; the code says pass
    results = client.requests[2]["messages"][-1]["content"]
    assert results[0]["type"] == "tool_result" and json.loads(results[0]["content"])["passed"] is True


def test_baseline_without_a_final_draft_is_a_failed_run():
    metrics = run_baseline(load_inputs(MOCK), client=FakeClient([[text("I could not finish.")]]))
    assert metrics["outcome"] == "no_valid_draft" and metrics["fully_staffed_shifts"] == 0


def test_baseline_tools_reject_a_bad_draft_without_crashing():
    inputs = load_inputs(MOCK)
    assert "error" in json.loads(run_tool("check_rules", {"draft": {"nope": 1}}, inputs))
    assert "error" in json.loads(run_tool("unknown", {}, inputs))
    assert score(inputs, {"final_draft": 5}, 1)["outcome"] == "no_valid_draft"


def test_planted_draft_is_round_1_then_the_live_scheduler_takes_over():
    inputs, planted = load_scenario("case_04")
    live = ScriptedScheduler([REFERENCE])
    result = run_phase1(run_eval.PlantedFirstScheduler(planted, live), run_eval.HintingRulesChecker(), inputs)
    assert result.rounds[0].hard_violations == 1 and result.outcome == "passed" and result.rounds_used == 2
    assert live.calls[0]["version"] == 2 and len(live.calls[0]["violations"]) == 1


def test_eval_cases_13_and_14_pass_in_code():
    assert run_eval.case_13()["pass"] is True
    report = run_eval.case_14()
    assert report["pass"] is True and all(report[k]["outcome"] != "passed" for k in ("A_missing", "B_unparseable", "C_stale"))
