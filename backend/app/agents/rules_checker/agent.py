"""The real Rules Checker agent: adds one fix_hint to each hard violation that check_rules already found.

Plugs into the Phase 1 harness through the `RulesChecker` protocol. It never decides pass or fail:
the harness keeps the code's violation list and only copies matching hints onto it.
"""

import json
from pathlib import Path
from typing import Any, List

from app.agents.common import MAX_TOKENS, make_client, parse_reply, reply_text, send
from app.config import MODEL
from app.contract.models import Draft, Violation
from app.harness.phase1 import Phase1Inputs

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "rules_checker_v0.md"


def build_message(draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> str:
    """The prompt's labeled fields as one JSON object. Only hard violations are sent (soft ones are not hinted)."""
    payload = {
        "violations": [v.model_dump(mode="json") for v in violations if v.severity == "hard"],
        "draft": draft.model_dump(mode="json"),
        "roster": [n.model_dump(mode="json") for n in inputs.roster],
        "rules": inputs.rules.model_dump(mode="json"),
        "availability": [r.model_dump(mode="json") for r in inputs.availability],
    }
    return json.dumps(payload, separators=(",", ":"))


class AnthropicRulesChecker:
    def __init__(self, client: Any = None, model: str = MODEL):
        self.client = client if client is not None else make_client()
        self.model = model
        self.system_prompt = PROMPT_PATH.read_text()
        self.calls: List[dict] = []

    def add_fix_hints(self, draft: Draft, violations: List[Violation], inputs: Phase1Inputs) -> List[Violation]:
        reply = send(
            self.client,
            model=self.model, max_tokens=MAX_TOKENS, system=self.system_prompt,
            messages=[{"role": "user", "content": build_message(draft, violations, inputs)}],
        )
        self.calls.append({"stop_reason": getattr(reply, "stop_reason", None)})
        parsed = parse_reply(reply_text(reply))
        if not isinstance(parsed, list):
            raise ValueError("the Rules Checker did not return a JSON array")
        return [Violation(**item) for item in parsed]  # a bad row raises; the harness then uses the code's list
