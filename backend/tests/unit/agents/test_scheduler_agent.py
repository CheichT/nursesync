"""The Scheduler agent wrapper, tested with a fake client so no API call is made."""

import json
from pathlib import Path
from types import SimpleNamespace

from app.agents.scheduler.agent import AnthropicScheduler, build_message, parse_reply
from app.harness.phase1 import load_inputs, run_phase1
from app.harness.stand_ins import HintingRulesChecker

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock"
REFERENCE = json.loads((MOCK / "reference_draft.json").read_text())


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        text = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               usage=SimpleNamespace(output_tokens=1))


def test_round_1_message_has_the_labeled_fields_and_no_fix_inputs():
    data = json.loads(build_message("case-1", "snap", 1, load_inputs(MOCK), None, []))
    assert set(data) == {"case_id", "snapshot_id", "version", "rules", "demand", "availability", "roster"}
    assert len(data["demand"]) == 14 and len(data["roster"]) == 24 and data["version"] == 1


def test_fix_round_message_adds_violations_and_previous_draft():
    from app.contract.models import Draft
    data = json.loads(build_message("case-1", "snap", 2, load_inputs(MOCK), Draft(**REFERENCE), []))
    assert data["violations"] == [] and data["previous_draft"]["case_id"] == "case-1"


def test_reply_parsing_accepts_plain_and_fenced_json_and_rejects_text():
    assert parse_reply('{"a": 1}') == {"a": 1}
    assert parse_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_reply("Here is your schedule: {}") is None


def test_uses_kerrians_prompt_as_the_system_prompt_and_runs_in_the_harness():
    client = FakeClient([json.dumps(REFERENCE)])
    scheduler = AnthropicScheduler(client=client)
    result = run_phase1(scheduler, HintingRulesChecker(), load_inputs(MOCK))
    assert result.outcome == "passed" and result.rounds_used == 1
    assert "Scheduler agent" in client.requests[0]["system"]
    assert client.requests[0]["model"] == "claude-sonnet-5-5"


def test_a_reply_that_is_not_json_is_a_failed_round_never_a_pass():
    client = FakeClient(["I could not do it."] * 3)
    result = run_phase1(AnthropicScheduler(client=client), HintingRulesChecker(), load_inputs(MOCK))
    assert result.outcome == "stopped_after_3_rounds" and result.final_draft is None


def test_a_call_out_run_sends_the_locked_assignments_and_affected_shifts():
    from app.contract.case_record import ShiftRef
    from app.contract.models import Draft
    inputs = load_inputs()
    draft = Draft(**REFERENCE)
    locked = [a for a in draft.assignments if (a.date, a.shift) != ("2026-11-04", "day")]
    earlier = [a for a in draft.assignments if (a.date, a.shift) == ("2026-11-04", "day") and a.nurse_id != "N006"]
    call_out = inputs.model_copy(update={"locked_assignments": locked, "earlier_assignments": earlier,
                                         "affected_shifts": [ShiftRef(date="2026-11-04", shift="day")]})
    sent = json.loads(build_message("case-2", "snap-case-2", 1, call_out, None, []))
    assert sent["mode"] == "call_out" and sent["affected_shifts"] == [{"date": "2026-11-04", "shift": "day"}]
    assert len(sent["locked_assignments"]) == len(locked) and len(sent["earlier_assignments"]) == len(earlier)
    plain = json.loads(build_message("case-1", "snap-case-1", 1, inputs, None, []))
    assert "mode" not in plain and "locked_assignments" not in plain  # a weekly run is unchanged
