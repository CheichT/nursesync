"""What the Demand and Availability agents hand back, and how their free-text extras are cleaned. Owner: Cheich.

Besides rows, the agents' replies carry advisory extras for the manager: `unusual` (one-line notes about odd days) and
`needs_manual_review` (items such as a day with no data or a nurse with partial data). They are untrusted text and they
never decide anything: code, not an agent, writes row status and decides whether a run stops. So extras are cleaned
(one line, no control characters, length and count caps) and a malformed item is dropped without touching the rows.
A plain list of rows is still a valid agent result, so scripted agents and older code keep working.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, List

from app.contract.models import NeedsManualReview
from app.harness.phase1 import _clean

log = logging.getLogger("nursesync.agent_output")

MAX_ITEMS = 20
MAX_NOTE_CHARS = 300
MAX_ID_CHARS = 100
ITEM_TYPES = ("demand_day", "nurse")


@dataclass
class AgentOutput:
    rows: Any
    unusual: List[Any] = field(default_factory=list)
    needs_manual_review: List[Any] = field(default_factory=list)


def clean_notes(raw: Any) -> List[str]:
    """The agent's `unusual` lines as clean one-line strings (at most 20, each at most 300 characters)."""
    if not isinstance(raw, list):
        return []
    notes = [_clean(x, MAX_NOTE_CHARS) for x in raw if isinstance(x, str)]
    notes = [n for n in notes if n]
    if len(notes) > MAX_ITEMS or len(notes) < len(raw):
        log.warning("agent notes: kept %d of %d", min(len(notes), MAX_ITEMS), len(raw))
    return notes[:MAX_ITEMS]


def clean_review(raw: Any) -> List[NeedsManualReview]:
    """The agent's needs_manual_review items, keeping only well-formed ones (type demand_day or nurse, an id, a note)."""
    if not isinstance(raw, list):
        return []
    kept: List[NeedsManualReview] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("item_type") not in ITEM_TYPES:
            continue
        ident, note = item.get("id"), item.get("note")
        if not isinstance(ident, str) or not isinstance(note, str) or not _clean(ident, MAX_ID_CHARS):
            continue
        kept.append(NeedsManualReview(item_type=item["item_type"], id=_clean(ident, MAX_ID_CHARS),
                                      note=_clean(note, MAX_NOTE_CHARS)))
    if len(kept) < len(raw):
        log.warning("agent review items: kept %d of %d", min(len(kept), MAX_ITEMS), len(raw))
    return kept[:MAX_ITEMS]


def merge_review(*lists: List[NeedsManualReview]) -> List[NeedsManualReview]:
    """One list with no repeats (same item_type and id). The first list wins, so code's own items come first."""
    seen = set()
    merged: List[NeedsManualReview] = []
    for items in lists:
        for item in items:
            key = (item.item_type, item.id)
            if key not in seen:
                seen.add(key)
                merged.append(item)
    return merged
