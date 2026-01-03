from __future__ import annotations

import json
from datetime import time
from pathlib import Path

from planner_ai.models import DailyRoutine


def _time_to_str(t: time) -> str:
    """Convert time to HH:MM string."""
    return t.strftime("%H:%M")


def _str_to_time(s: str) -> time:
    """Convert HH:MM string to time."""
    h, m = map(int, s.split(":"))
    return time(h, m)


class RoutineStore:
    def __init__(self, path: str = "data/routine.json"):
        self.path = Path(path)

    def load(self) -> DailyRoutine:
        """
        Load daily routine from disk. Returns defaults if file is missing or invalid.
        """
        try:
            if not self.path.exists():
                return DailyRoutine()

            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Convert time strings back to time objects
            if "blocked_slots" in data:
                data["blocked_slots"] = [
                    (_str_to_time(s), _str_to_time(e)) for s, e in data["blocked_slots"]
                ]
            if "lunch_start" in data and isinstance(data["lunch_start"], str):
                data["lunch_start"] = _str_to_time(data["lunch_start"])
            if "lunch_end" in data and isinstance(data["lunch_end"], str):
                data["lunch_end"] = _str_to_time(data["lunch_end"])
            return DailyRoutine(**data)
        except Exception:
            return DailyRoutine()

    def save(self, routine: DailyRoutine) -> None:
        """
        Save daily routine to disk.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = routine.model_dump()
        # Convert time objects to strings for JSON
        if "blocked_slots" in data:
            data["blocked_slots"] = [
                [_time_to_str(s), _time_to_str(e)] for s, e in data["blocked_slots"]
            ]
        if isinstance(data.get("lunch_start"), time):
            data["lunch_start"] = _time_to_str(data["lunch_start"])
        if isinstance(data.get("lunch_end"), time):
            data["lunch_end"] = _time_to_str(data["lunch_end"])
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
