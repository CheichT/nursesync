"""Where the Demand and Availability agents read their raw data (their `get_demand` / `get_availability` tools).

`MockSource` reads the mock files, so tests and demos need no Shift Board. A real source (Shift Board) plugs
in later with the same two methods. Demand gives patient counts only: the agent works out nurses_needed.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Protocol

from app.contract.case_record import Snapshot
from app.harness.phase1 import DEFAULT_DATA


class DataSource(Protocol):
    def get_demand(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        """Rows of unit, date, shift, patient_count for the snapshot's unit and week."""

    def get_availability(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        """Rows of nurse_id, date, shift, available, reason for the snapshot's roster and week."""

    def get_callouts(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        """Call-outs reported for the snapshot's roster and week: nurse_id, date, shift, reported_at."""


class MockSource:
    def __init__(self, data_dir: Path = DEFAULT_DATA):
        self.data_dir = Path(data_dir)

    def _read(self, name: str) -> List[Dict[str, Any]]:
        return json.loads((self.data_dir / name).read_text())

    def get_demand(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        from app.orchestrator import week_dates
        days = set(week_dates(snapshot.week_start))
        return [{k: r[k] for k in ("unit", "date", "shift", "patient_count")}
                for r in self._read("demand.json") if r["unit"] == snapshot.unit and r["date"] in days]

    def get_availability(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        from app.orchestrator import week_dates
        days = set(week_dates(snapshot.week_start))
        ids = {n.nurse_id for n in snapshot.roster}
        return [{k: r[k] for k in ("nurse_id", "date", "shift", "available", "reason")}
                for r in self._read("availability.json") if r["nurse_id"] in ids and r["date"] in days]

    def get_callouts(self, snapshot: Snapshot) -> List[Dict[str, Any]]:
        """The folder's callouts.json, if it has one (the base mock week has none). Roster and week only."""
        from app.orchestrator import week_dates
        path = self.data_dir / "callouts.json"
        if not path.exists():
            return []
        days = set(week_dates(snapshot.week_start))
        ids = {n.nurse_id for n in snapshot.roster}
        return [r for r in json.loads(path.read_text()) if r["nurse_id"] in ids and r["date"] in days]
