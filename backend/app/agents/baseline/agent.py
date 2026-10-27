"""The single-agent baseline (eval case 7): one agent does the whole job with four tools, using Kerrian's prompt.

The baseline reports its own pass/fail, but that is never trusted. `run_baseline` re-runs `check_rules` on its
final draft and records those numbers; the self-report is kept only to see whether the agent told the truth.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents.common import MAX_TOKENS, make_client, parse_reply, reply_text, send
from app.config import MODEL
from app.contract.models import Draft
from app.harness.phase1 import Phase1Inputs
from app.harness.rules import DraftRejected, check_rules_from_dicts

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "baseline_v0.md"
MAX_TURNS = 30  # tool-use turns; stops a runaway loop

TOOLS = [
    {"name": "get_demand", "description": "Read how many nurses each unit, date and shift needs.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_availability", "description": "Read who can work each nurse, date and shift.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_roster", "description": "Read each nurse's id, unit, certifications and hours_this_week.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "check_rules", "description": "Test a draft. Returns pass or fail and every violation found.",
     "input_schema": {"type": "object", "properties": {"draft": {"type": "object"}}, "required": ["draft"]}},
]


def run_tool(name: str, tool_input: Dict[str, Any], inputs: Phase1Inputs) -> str:
    dump = lambda rows: json.dumps([r.model_dump(mode="json") for r in rows], separators=(",", ":"))
    if name == "get_demand":
        return dump(inputs.demand)
    if name == "get_availability":
        return dump(inputs.availability)
    if name == "get_roster":
        return dump(inputs.roster)
    if name == "check_rules":
        try:
            result = check_rules_from_dicts(tool_input.get("draft", {}), inputs.demand, inputs.availability,
                                            inputs.roster, inputs.rules)
        except DraftRejected as err:
            return json.dumps({"error": f"draft rejected: {err}"})
        return result.model_dump_json()
    return json.dumps({"error": f"unknown tool {name}"})


def run_baseline(inputs: Phase1Inputs, case_id: str = "case-1", snapshot_id: str = "phase1-snapshot",
                 client: Any = None, model: str = MODEL) -> Dict[str, Any]:
    """Run the baseline once. Returns the recomputed metrics (never the agent's own claims)."""
    client = client if client is not None else make_client()
    system = PROMPT_PATH.read_text()
    messages: List[Dict[str, Any]] = [{"role": "user", "content": json.dumps(
        {"case_id": case_id, "snapshot_id": snapshot_id, "version": 1})}]
    final: Optional[Any] = None
    turns = 0
    for turns in range(1, MAX_TURNS + 1):
        reply = send(client, model=model, max_tokens=MAX_TOKENS, system=system, tools=TOOLS,
                                       messages=messages)
        calls = [b for b in reply.content if getattr(b, "type", "") == "tool_use"]
        if not calls:
            final = parse_reply(reply_text(reply))
            break
        messages.append({"role": "assistant", "content": reply.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input, inputs)} for b in calls]})
    return score(inputs, final, turns)


def score(inputs: Phase1Inputs, final: Any, turns: int) -> Dict[str, Any]:
    """Recompute the case 7 metrics with check_rules. No usable final draft counts as a failed run."""
    base = {"turns": turns, "shifts_in_week": len(inputs.demand)}
    draft = final.get("final_draft") if isinstance(final, dict) else None
    try:
        result = check_rules_from_dicts(draft, inputs.demand, inputs.availability, inputs.roster, inputs.rules)
    except (DraftRejected, TypeError, AttributeError) as err:
        return {**base, "outcome": "no_valid_draft", "error": str(err)[:200], "hard_violation_count": None,
                "fully_staffed_shifts": 0, "coverage_rate": 0.0}
    parsed = Draft(**draft)
    counts: Dict[tuple, int] = {}
    for a in parsed.assignments:
        counts[(a.unit, a.date, a.shift)] = counts.get((a.unit, a.date, a.shift), 0) + 1
    staffed = sum(1 for d in inputs.demand if counts.get((d.unit, d.date, d.shift), 0) == d.nurses_needed)
    hard = sum(1 for v in result.violations if v.severity == "hard")
    return {**base, "outcome": "passed" if result.passed else "failed", "hard_violation_count": hard,
            "fully_staffed_shifts": staffed, "coverage_rate": round(staffed / len(inputs.demand), 3),
            "self_report_matches": final.get("check_rules_passed") == result.passed}
