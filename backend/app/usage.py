"""A daily cap on paid operations (weekly runs and demand changes). Owner: Cheich.

Each paid operation runs live agents and costs real money (about $0.30 to $1.50). The cap counts operations, not dollars:
a dollar cap needs price assumptions that can be wrong, a count does not. The count is saved in a file so a restart
does not reset it. An operation is counted when it is accepted, before it runs, even if it later fails (the money may
already be spent). If the file cannot be read, the meter refuses everything rather than guess.
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("nursesync.usage")

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "usage.json"
DEFAULT_MAX_PER_DAY = 10
ENV_NAME = "NURSESYNC_MAX_PAID_OPS_PER_DAY"


class SpendCapReached(Exception):
    """The daily limit is used up. The message is plain language, safe to show the manager."""


def max_from_env() -> int:
    raw = os.environ.get(ENV_NAME)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_PER_DAY
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        log.warning("%s=%r is not a whole number of 0 or more; using %d", ENV_NAME, raw, DEFAULT_MAX_PER_DAY)
        return DEFAULT_MAX_PER_DAY


class UsageMeter:
    def __init__(self, path: Path = DEFAULT_PATH, max_per_day: Optional[int] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self.path = Path(path)
        self.max_per_day = max_from_env() if max_per_day is None else max_per_day
        self._clock = clock or datetime.now
        self._lock = threading.Lock()

    def _today(self) -> str:
        return self._clock().date().isoformat()

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"date": self._today(), "events": []}
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ValueError("unexpected shape")
        if data.get("date") != self._today():
            return {"date": self._today(), "events": []}  # a new day starts at zero
        return data

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, self.path)  # all or nothing

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            used = len(self._read()["events"])
        return {"used_today": used, "max_per_day": self.max_per_day,
                "remaining": max(self.max_per_day - used, 0), "date": self._today()}

    def try_spend(self, kind: str, case_id: str = "") -> None:
        """Count one paid operation, or raise SpendCapReached (and count nothing)."""
        with self._lock:
            try:
                data = self._read()
            except (ValueError, OSError) as err:
                log.error("usage file %s is unreadable: %s", self.path, err)
                raise SpendCapReached(f"The usage file {self.path.name} cannot be read, so paid runs are stopped to be "
                                      "safe. Fix or delete the file to continue.")
            if len(data["events"]) >= self.max_per_day:
                raise SpendCapReached(
                    f"The daily limit of {self.max_per_day} paid operations is used up. Try again tomorrow, or raise "
                    f"{ENV_NAME} and restart the server.")
            data["events"].append({"at": self._clock().isoformat(timespec="seconds"), "kind": kind, "case_id": case_id})
            self._write(data)
