"""Persists each run so the next one can report what changed.

Actions are tracked by a fingerprint of their driving numbers, so a rerun can
say whether a condition is new, moving, or unchanged since the last brief.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from . import config
from .models import Action

STATE_FILE = config.STATE_DIR / "last_run.json"


def load(state_file: Path = STATE_FILE) -> dict[str, str]:
    if not state_file.exists():
        return {}
    try:
        with open(state_file, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def save(actions: Iterable[Action], state_file: Path = STATE_FILE) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as fh:
        json.dump({a.id: a.fingerprint for a in actions}, fh, indent=2, sort_keys=True)


def change_note(action: Action, previous: dict[str, str]) -> str:
    if action.id not in previous:
        return "New since last brief."
    return "Unchanged since last brief." if previous[action.id] == action.fingerprint \
        else "Changed since last brief."
