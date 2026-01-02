from __future__ import annotations

from typing import Optional, Any

from planner_ai.models import Task
from llm.llm_client import LLMClient
from storage.preferences_store import PreferencesStore


class TaskClassifier:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        preferences_store: Optional[PreferencesStore] = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.preferences_store = preferences_store or PreferencesStore()

    def classify(self, tasks: list[Task]) -> list[Task]:
        """
        Classify tasks using LLM (UC3).
        Returns updated Task models (category + priority). Falls back safely.
        """
        if not tasks:
            return []

        # Ensure we work with Task models
        normalized: list[Task] = [t if isinstance(t, Task) else Task(**t) for t in tasks]

        # Preferences can be used later for better prompts/rules; keep it loaded and available
        _prefs = self.preferences_store.load()

        payload = [t.model_dump() for t in normalized]
        classified = self.llm_client.classify_tasks(payload)

        if not classified:
            return normalized

        out: list[Task] = []
        for item in classified:
            task = self._merge_task(normalized, item)
            if task is not None:
                out.append(task)

        # If LLM returned fewer tasks, keep the rest unchanged
        if len(out) < len(normalized):
            existing_titles = {t.title for t in out}
            for t in normalized:
                if t.title not in existing_titles:
                    out.append(t)

        return out

    def _merge_task(self, original: list[Task], item: Any) -> Optional[Task]:
        """
        Merge LLM classification result back into Task.
        Title is used as a stable key in this minimal implementation.
        """
        try:
            if isinstance(item, Task):
                return item

            if not isinstance(item, dict):
                return None

            item = dict(item)
            title = (item.get("title") or "").strip()
            if not title:
                return None

            # Find the original task by title
            base = next((t for t in original if t.title == title), None)
            if base is None:
                # If not found, still accept it as a new Task
                base = Task(title=title)

            category = (item.get("category") or base.category or "other").strip().lower()
            priority = item.get("priority", base.priority if base.priority is not None else 3)

            try:
                priority = int(priority)
            except (TypeError, ValueError):
                priority = 3
            if priority < 1:
                priority = 1
            if priority > 5:
                priority = 5

            merged = base.model_copy(update={"category": category, "priority": priority})
            return merged
        except Exception:
            return None
