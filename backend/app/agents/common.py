"""Small helpers shared by the live agents (client setup and reply parsing)."""

import json
import re
from typing import Any, Optional

from app.config import load_api_key

# Longer than the visible reply needs: the model thinks before it answers, and that counts toward the limit.
MAX_TOKENS = 32000
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def make_client() -> Any:
    import anthropic
    return anthropic.Anthropic(api_key=load_api_key())


def reply_text(reply: Any) -> str:
    return "".join(block.text for block in reply.content if getattr(block, "type", "") == "text")


def parse_reply(text: str) -> Optional[Any]:
    """The reply as a JSON value, or None if it is not valid JSON (the harness then counts a failed round)."""
    text = text.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError:
        return None


def send(client: Any, **kwargs: Any) -> Any:
    """One model call. Streams when the client can (the SDK requires it for long replies), else a plain call."""
    messages = client.messages
    if hasattr(messages, "stream"):
        with messages.stream(**kwargs) as stream:
            return stream.get_final_message()
    return messages.create(**kwargs)


def run_tool_loop(client: Any, model: str, system: str, user_message: str, tools: list,
                  run_tool: Any, max_turns: int = 10) -> Any:
    """Send one message, answer any tool calls, and return the final reply (the one with no tool call).

    Raises RuntimeError when the loop runs out of turns or the reply was cut off (max_tokens), because a
    cut-off JSON reply must never be read as an answer."""
    messages: list = [{"role": "user", "content": user_message}]
    for _ in range(max_turns):
        reply = send(client, model=model, max_tokens=MAX_TOKENS, system=system, tools=tools, messages=messages)
        calls = [b for b in reply.content if getattr(b, "type", "") == "tool_use"]
        if not calls:
            if getattr(reply, "stop_reason", None) == "max_tokens":
                raise RuntimeError("the reply was cut off (max_tokens); the answer is incomplete")
            return reply
        messages.append({"role": "assistant", "content": reply.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)} for b in calls]})
    raise RuntimeError(f"the agent did not finish within {max_turns} tool turns")
