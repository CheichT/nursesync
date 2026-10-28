"""Saves case records as one JSON file each. Owner: Cheich. Version 0: a folder of files, swappable later.

Only these state changes are allowed on a saved case, so a decided case can never be quietly changed:
  building -> waiting_approval
  waiting_approval -> approved | rejected | out_of_date
A new case can be saved in any state. Saving the same state again (no change) is refused for decided cases.
Not safe for two people writing at the same moment: there is no real login or locking yet.
"""

import json
import os
import re
from pathlib import Path
from typing import Callable, List

from app.contract.case_record import CaseRecord

DEFAULT_FOLDER = Path(__file__).resolve().parents[1] / "data" / "cases"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_ALLOWED = {
    "building": {"waiting_approval"},
    "waiting_approval": {"approved", "rejected", "out_of_date"},
}


class CaseStoreError(Exception):
    """The case could not be saved or loaded. The message is plain language."""


class CaseStore:
    def __init__(self, folder: Path = DEFAULT_FOLDER):
        self.folder = Path(folder)

    def _path(self, case_id: str) -> Path:
        if not _SAFE_ID.fullmatch(case_id):
            raise CaseStoreError(f"not a valid case id: {case_id!r} (letters, digits, - and _ only)")
        return self.folder / f"{case_id}.json"

    def exists(self, case_id: str) -> bool:
        return self._path(case_id).exists()

    def load(self, case_id: str) -> CaseRecord:
        path = self._path(case_id)
        if not path.exists():
            raise CaseStoreError(f"no saved case {case_id}")
        try:
            return CaseRecord.model_validate(json.loads(path.read_text()))
        except ValueError as err:
            raise CaseStoreError(f"case {case_id} could not be read: {str(err).splitlines()[0]}")

    def save(self, record: CaseRecord) -> None:
        path = self._path(record.case_id)
        if path.exists():
            old = self.load(record.case_id)
            if record.status not in _ALLOWED.get(old.status, set()):
                raise CaseStoreError(f"case {record.case_id} is {old.status} and cannot become {record.status}")
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(record.model_dump_json(indent=2))
        os.replace(tmp, path)  # all or nothing: a crash never leaves half a file

    def update(self, case_id: str, change: Callable[[CaseRecord], CaseRecord]) -> CaseRecord:
        """Load a case, apply a decision function (for example `approve`), save it, and return the new record.
        Nothing is saved if the decision is refused."""
        record = change(self.load(case_id))
        self.save(record)
        return record

    def list_ids(self) -> List[str]:
        return sorted(p.stem for p in self.folder.glob("*.json")) if self.folder.is_dir() else []
