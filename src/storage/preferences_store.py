from __future__ import annotations

import json
from pathlib import Path

from planner_ai.models import UserPreferences


class PreferencesStore:
    def __init__(self, path: str = "data/preferences.json"):
        self.path = Path(path)

    def load(self) -> UserPreferences:
        """
        Load user preferences from disk. Returns defaults if file is missing or invalid.
        """
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
            json.dumps(prefs.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
