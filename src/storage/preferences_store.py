from __future__ import annotations

import json
from datetime import time
from pathlib import Path

from planner_ai.models import UserPreferences


def _time_to_str(t: time) -> str:
    return t.strftime("%H:%M")


def _str_to_time(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


class PreferencesStore:
    def __init__(self, path: str = "data/preferences.json"):
        self.path = Path(path)

    def load(self) -> UserPreferences:
        try:
            if not self.path.exists():
                return UserPreferences()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return UserPreferences(**data)
        except Exception:
            return UserPreferences()

    def save(self, prefs: UserPreferences) -> None:
        """
        Save user preferences to disk.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            prefs.model_dump_json(ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

