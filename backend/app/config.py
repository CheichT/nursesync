"""Settings read from the environment. The API key lives only in the repo-root `.env` file (never committed).

Only variable names appear here. Never print or log the key.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-sonnet-5-5"


def load_api_key() -> str:
    """Return ANTHROPIC_API_KEY from `.env` or the environment. Raises a plain error if it is missing."""
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or key == "your-key-here":
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Put it in the .env file at the repo root.")
    return key
