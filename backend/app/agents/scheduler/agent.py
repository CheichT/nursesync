"""The real Scheduler agent: sends one week of data to Claude with Kerrian's prompt and returns the draft.

Plugs into the Phase 1 harness through the `Scheduler` protocol (see app/harness/phase1.py).
The message layout is the one Kerrian's prompt describes: one JSON object with labeled fields.
Anything the model returns is only a draft: the harness validates it and `check_rules` judges it.
"""

import json
from pathlib import Path
from typing import Any, List, Optional

from app.agents.common import MAX_TOKENS, make_client, parse_reply, reply_text, send
from app.config import MODEL
from app.contract.models import Draft, Violation
from app.harness.phase1 import Phase1Inputs

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "scheduler_v0.md"


def build_message(case_id: str, snapshot_id: str, version: int, inputs: Phase1Inputs,
                  previous_draft: Optional[Draft], violations: List[Violation]) -> str:
    """The user message: the prompt's labeled fields as one JSON object. Rounds 2 and 3 add the fix inputs."""
    payload = {
        "case_id": case_id,
        "snapshot_id": snapshot_id,
        "version": version,
        "rules": inputs.rules.model_dump(mode="json"),
        "demand": [r.model_dump(mode="json") for r in inputs.demand],
        "availability": [r.model_dump(mode="json") for r in inputs.availability],
        "roster": [n.model_dump(mode="json") for n in inputs.roster],
    }
    if version > 1:
        payload["violations"] = [v.model_dump(mode="json") for v in violations]
        payload["previous_draft"] = previous_draft.model_dump(mode="json") if previous_draft else None
    return json.dumps(payload, separators=(",", ":"))


class AnthropicScheduler:
    def __init__(self, client: Any = None, case_id: str = "case-1", snapshot_id: str = "phase1-snapshot",
                 model: str = MODEL):
        if client is None:
            client = make_client()
        self.client = client
        self.case_id = case_id
        self.snapshot_id = snapshot_id
        self.model = model
        self.system_prompt = PROMPT_PATH.read_text()
        self.calls: List[dict] = []
        self.last_text = ""  # the raw reply, kept for debugging

    def build(self, version: int, inputs: Phase1Inputs, previous_draft: Optional[Draft],
              violations: List[Violation]) -> Any:
        message = build_message(self.case_id, self.snapshot_id, version, inputs, previous_draft, violations)
        reply = send(
            self.client,
            model=self.model, max_tokens=MAX_TOKENS, system=self.system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        text = reply_text(reply)
        self.last_text = text
        self.calls.append({"version": version, "stop_reason": getattr(reply, "stop_reason", None),
                           "output_tokens": getattr(getattr(reply, "usage", None), "output_tokens", None)})
        return parse_reply(text)
