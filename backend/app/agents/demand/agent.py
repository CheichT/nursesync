"""The real Demand agent: reads patient counts with its `get_demand` tool and returns one row per shift.

Plugs into the orchestrator through the `DemandAgent` protocol (app/orchestrator.py). It uses Kerrian's
prompt (prompts/demand_v0.md). The agent never writes `status`: the orchestrator does. A non-empty row
`note` becomes a `flag`, which the orchestrator turns into needs_review.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.agents.common import make_client, parse_reply, reply_text, run_tool_loop
from app.agents.data_source import DataSource, MockSource
from app.agent_output import AgentOutput
from app.config import MODEL
from app.contract.case_record import Snapshot

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "demand_v0.md"
TOOLS = [{"name": "get_demand", "description": "Read Shift Board patient counts for the unit and week.",
          "input_schema": {"type": "object", "properties": {}}}]


def rows_from_reply(parsed: Any) -> List[Dict[str, Any]]:
    """The reply's rows, with each non-empty `note` copied to `flag`. Anything else is an error."""
    rows = parsed.get("rows") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        raise ValueError("the reply is not a JSON object with a list of rows")
    out = []
    for r in rows:
        if isinstance(r, dict):
            r = {k: v for k, v in r.items() if k != "status"}  # status is never the agent's to write
            note = r.pop("note", "")
            if isinstance(note, str) and note.strip():
                r["flag"] = note.strip()
        out.append(r)
    return out


class AnthropicDemandAgent:
    def __init__(self, client: Any = None, source: DataSource = None, model: str = MODEL):
        self.client = client if client is not None else make_client()
        self.source = source if source is not None else MockSource()
        self.model = model
        self.system_prompt = PROMPT_PATH.read_text()
        self.last_text = ""

    def run(self, snapshot: Snapshot) -> AgentOutput:
        def run_tool(name: str, tool_input: Dict[str, Any]) -> str:
            if name != "get_demand":
                return json.dumps({"error": f"unknown tool {name}"})
            try:
                return json.dumps(self.source.get_demand(snapshot), separators=(",", ":"))
            except Exception as err:
                return json.dumps({"error": f"get_demand failed: {err}"})

        message = json.dumps({
            "snapshot_id": snapshot.snapshot_id, "unit": snapshot.unit, "week_start": snapshot.week_start,
            "rules": {"ratio_patients_per_nurse": snapshot.rules.ratio_patients_per_nurse},
        }, separators=(",", ":"))
        reply = run_tool_loop(self.client, self.model, self.system_prompt, message, TOOLS, run_tool)
        self.last_text = reply_text(reply)
        parsed = parse_reply(self.last_text)
        rows = rows_from_reply(parsed)
        return AgentOutput(rows=rows, unusual=parsed.get("unusual", []), needs_manual_review=parsed.get("needs_manual_review", []))
