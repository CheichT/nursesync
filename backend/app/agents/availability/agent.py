"""The real Availability agent: reads each nurse's availability with `get_availability`, one row per nurse and shift.

Plugs into the orchestrator through the `AvailabilityAgent` protocol. It uses Kerrian's prompt
(prompts/availability_v0.md). Phase 2 skips `get_callouts` (call-outs are Phase 3). The agent never writes
`status`. A non-empty row `note` becomes a `flag`, which the orchestrator turns into needs_review.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.agents.common import make_client, parse_reply, reply_text, run_tool_loop
from app.agents.data_source import DataSource, MockSource
from app.agents.demand.agent import rows_from_reply
from app.agent_output import AgentOutput
from app.config import MODEL
from app.contract.case_record import Snapshot

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "availability_v0.md"
TOOLS = [{"name": "get_availability", "description": "Read each nurse's availability and approved leave for the week.",
          "input_schema": {"type": "object", "properties": {}}}]


class AnthropicAvailabilityAgent:
    def __init__(self, client: Any = None, source: DataSource = None, model: str = MODEL):
        self.client = client if client is not None else make_client()
        self.source = source if source is not None else MockSource()
        self.model = model
        self.system_prompt = PROMPT_PATH.read_text()
        self.last_text = ""

    def run(self, snapshot: Snapshot) -> AgentOutput:
        def run_tool(name: str, tool_input: Dict[str, Any]) -> str:
            if name != "get_availability":
                return json.dumps({"error": f"unknown tool {name}"})
            try:
                return json.dumps(self.source.get_availability(snapshot), separators=(",", ":"))
            except Exception as err:
                return json.dumps({"error": f"get_availability failed: {err}"})

        message = json.dumps({
            "snapshot_id": snapshot.snapshot_id, "unit": snapshot.unit, "week_start": snapshot.week_start,
            "roster": [{"nurse_id": n.nurse_id, "name": n.name} for n in snapshot.roster],
        }, separators=(",", ":"))
        reply = run_tool_loop(self.client, self.model, self.system_prompt, message, TOOLS, run_tool)
        self.last_text = reply_text(reply)
        parsed = parse_reply(self.last_text)
        rows = rows_from_reply(parsed)
        return AgentOutput(rows=rows, unusual=[], needs_manual_review=parsed.get("needs_manual_review", []))
