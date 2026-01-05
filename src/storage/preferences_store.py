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

            # backwards/robust: convert focus times from strings
            if "focus_start" in data and isinstance(data["focus_start"], str):
                data["focus_start"] = _str_to_time(data["focus_start"])
            if "focus_end" in data and isinstance(data["focus_end"], str):
                data["focus_end"] = _str_to_time(data["focus_end"])

            return UserPreferences(**data)
        except Exception:
            return UserPreferences()

    def save(self, prefs: UserPreferences) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        data = prefs.model_dump()

        # convert time objects to strings for JSON
        if isinstance(data.get("focus_start"), time):
            data["focus_start"] = _time_to_str(data["focus_start"])
        if isinstance(data.get("focus_end"), time):
            data["focus_end"] = _time_to_str(data["focus_end"])

        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
