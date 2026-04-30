"""
IP-based trial gating with JSON file persistence.

Trial flow:
  1. Request arrives without an X-API-Key header → check trial count for IP
  2. If trials remain → consume one, allow request
  3. If trials exhausted → return 403 with setup instructions
  4. Request arrives with valid X-API-Key → always allowed, no trial consumed

Config via env:
  TRIAL_LIMIT  — max trials per IP (default: 2)
  API_KEYS     — comma-separated list of valid keys
  TRIAL_FILE   — path to trial data file (default: .trials.json)
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _trial_limit() -> int:
    return int(os.getenv("TRIAL_LIMIT", "2"))


def _trial_file() -> Path:
    return Path(os.getenv("TRIAL_DATA_FILE", ".trials.json"))


def _load() -> dict[str, int]:
    path = _trial_file()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save(data: dict[str, int]) -> None:
    path = _trial_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def trials_remaining(ip: str) -> int:
    """How many trials this IP has left (never negative)."""
    data = _load()
    used = data.get(ip, 0)
    return max(0, _trial_limit() - used)


def consume_trial(ip: str) -> bool:
    """Consume one trial for the IP.  Returns True if consumed, False if already at limit."""
    data = _load()
    used = data.get(ip, 0)
    if used >= _trial_limit():
        return False
    data[ip] = used + 1
    _save(data)
    return True


def validate_api_key(key: str | None) -> bool:
    """Check whether an API key is valid."""
    if not key:
        return False
    valid_keys = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
    return key in valid_keys
