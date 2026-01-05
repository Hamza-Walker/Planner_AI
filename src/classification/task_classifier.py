from __future__ import annotations

import logging
from typing import Optional, Any

from planner_ai.models import Task
from llm.llm_client import LLMClient
from storage.preferences_store import PreferencesStore

logger = logging.getLogger(__name__)


class TaskClassifier:
    """
    UC3 - Task classification (category + priority) using an LLM.
    Tier-aware behavior:
    - eco: prefer safe defaults (optionally skip LLM if needed)
    - fast: normal LLM classification
    - large: normal LLM classification (same API, different tier is mostly for upstream model choice)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        preferences_store: Optional[PreferencesStore] = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.preferences_store = preferences_store or PreferencesStore()

    def classify(self, tasks: list[Task], llm_tier: str = "large") -> list[Task]:
        """
        Classify tasks using LLM (UC3).
        Returns updated Task models (category + priority). Falls back safely.
        """
        tier = (llm_tier or "large").strip().lower()
        logger.info("TaskClassifier: classifying tasks (tier=%s, count=%d)", tier, len(tasks) if tasks else 0)

        if not tasks:
            return []

        normalized: list[Task] = [t if isinstance(t, Task) else Task(**t) for t in tasks]

        # Preferences can be used later for better prompts/rules; keep it loaded and available.
        _prefs = self.preferences_store.load()

        # ECO mode: avoid expensive classification. Use safe defaults.
        # This makes tier have a real effect even if LLMClient doesn't expose "tier" directly.
        if tier == "eco":
            out: list[Task] = []
            for t in normalized:
                category = (t.category or "other").strip().lower()
                priority = t.priority if t.priority is not None else 3
                out.append(t.model_copy(update={"category": category, "priority": int(priority)}))
            return out

        # FAST/LARGE: run LLM classification
        payload = [t.model_dump() for t in normalized]
        classified = self.llm_client.classify_tasks(payload)

        if not classified:
            logger.warning("TaskClassifier: empty classification result, returning original tasks")
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
