"""Run the local case API. Owner: Cheich.

    cd backend && ../.venv/bin/python -m app.serve [--port 8000] [--seed-samples]

It listens on 127.0.0.1 ONLY (this computer), and there is no login. There is deliberately no option to expose it.
Case records are read from and saved to backend/data/cases (gitignored).

--seed-samples copies the sample cases from docs/sample-cases into the store (the undecided version of each case,
skipping any id already there), so the approval UI has something to show.

Live agents (needed for change demand) cost money and are off by default. Turn them on with NURSESYNC_LIVE=1
and an ANTHROPIC_API_KEY in .env.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from app.api import create_app
from app.case_store import DEFAULT_FOLDER, CaseStore
from app.contract.case_record import CaseRecord
from app.sample_cases import OUT_DIR

HOST = "127.0.0.1"


def seed_samples(store: CaseStore, folder: Path = OUT_DIR) -> int:
    """Save each sample case the store does not have yet. Returns how many were added.

    Several sample files are the same case in different states (for example `passed` and `approved`), and a store
    holds one state per case id. So for each id only the undecided version (waiting_approval) is saved when there is
    one: a decision is something you do through the API, not something to seed."""
    by_id: dict = {}
    for path in sorted(Path(folder).glob("*.json")):
        record = CaseRecord.model_validate_json(path.read_text())
        best = by_id.get(record.case_id)
        if best is None or (record.status == "waiting_approval" and best.status != "waiting_approval"):
            by_id[record.case_id] = record
    added = 0
    for record in by_id.values():
        if not store.exists(record.case_id):
            store.save(record)
            added += 1
    return added


def build_app(store_dir: Path = DEFAULT_FOLDER, live: Optional[bool] = None):
    store = CaseStore(store_dir)
    live = os.environ.get("NURSESYNC_LIVE") == "1" if live is None else live
    if not live:
        return create_app(store)
    from app.agents.rules_checker.agent import AnthropicRulesChecker
    from app.agents.scheduler.agent import AnthropicScheduler
    from app.config import load_api_key
    load_api_key()  # fails now, with a plain message, if the key is missing (it is never printed)
    return create_app(store, lambda case_id, snapshot_id: AnthropicScheduler(case_id=case_id, snapshot_id=snapshot_id),
                      AnthropicRulesChecker())


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local NurseSync case API (this computer only, no login).")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--store-dir", default=str(DEFAULT_FOLDER), help="folder of case JSON files")
    parser.add_argument("--seed-samples", action="store_true", help="add the sample cases the store does not have")
    args = parser.parse_args(argv)

    if args.seed_samples:
        print(f"Added {seed_samples(CaseStore(Path(args.store_dir)))} sample case(s) to {args.store_dir}")
    import uvicorn
    app = build_app(Path(args.store_dir))
    print(f"NurseSync API on http://{HOST}:{args.port} (this computer only, no login). "
          f"Live agents: {'ON' if os.environ.get('NURSESYNC_LIVE') == '1' else 'off'}")
    uvicorn.run(app, host=HOST, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
