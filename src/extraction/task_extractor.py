from __future__ import annotations

from typing import Optional, Any

from planner_ai.models import Task
from llm.llm_client import LLMClient


class TaskExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def extract(self, note: str) -> list[Task]:
        """
        Extract actionable tasks from a daily note using LLM (UC2).
        Returns a list of Task models. Falls back to [] on any failure.
        """
        if not note or not note.strip():
            return []

        raw_tasks = self.llm_client.extract_tasks(note)

        if not raw_tasks:
            return []

        tasks: list[Task] = []
        for item in raw_tasks:
            task = self._to_task(item)
            if task is not None:
                tasks.append(task)

        return tasks

    def _to_task(self, item: Any) -> Optional[Task]:
        """
        Convert LLM output item to Task model safely.
        """
        try:
            if isinstance(item, Task):
                return item

            if isinstance(item, dict):
                # Minimal normalization / defaults
                item = dict(item)
                item.setdefault("estimated_duration_min", 30)

                title = (item.get("title") or "").strip()
                if not title:
                    return None

                item["title"] = title

                # Ensure positive duration
                try:
                    dur = int(item.get("estimated_duration_min", 30))
                except (TypeError, ValueError):
                    dur = 30
                if dur <= 0:
                    dur = 30
                item["estimated_duration_min"] = dur

                return Task(**item)

            return None
        except Exception:
            return None
