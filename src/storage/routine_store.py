from __future__ import annotations

import json
from pathlib import Path

from planner_ai.models import DailyRoutine


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
            return DailyRoutine(**data)
        except Exception:
            return DailyRoutine()

    def save(self, routine: DailyRoutine) -> None:
        """
        Save daily routine to disk.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(routine.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
