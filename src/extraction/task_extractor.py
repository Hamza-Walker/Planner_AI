import json
import logging
from typing import Optional

from planner_ai.models import Task
from llm.llm_client import LLMClient

logger = logging.getLogger(__name__)


class TaskExtractor:
    """
    UC2 - Task extraction from freeform notes using an LLM.
    Tier-aware prompts allow cheaper/faster modes with predictable behavior.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def _build_prompt(self, notes: str, llm_tier: str) -> str:
        """
        Build a tier-aware prompt. We keep it simple and robust:
        - Always request strict JSON output
        - Keep schema minimal to avoid hallucinated fields
        """
        tier = (llm_tier or "large").strip().lower()

        if tier == "eco":
            instruction = (
                "Extract the tasks from the notes. Be minimal and conservative. "
                "Only extract tasks that are clearly stated. "
                "Return strict JSON with this structure: "
                '{"tasks":[{"title": "...", "description": ""}]}.'
            )
        elif tier == "fast":
            instruction = (
                "Extract the tasks from the notes quickly and reliably. "
                "Return strict JSON with this structure: "
                '{"tasks":[{"title": "...", "description": ""}]}.'
            )
        else:
            # large / default: allow slightly smarter extraction, but still strict JSON
            instruction = (
                "Extract the tasks from the notes with high accuracy. "
                "You may infer a short description if it is obvious from the text. "
                "Return strict JSON with this structure: "
                '{"tasks":[{"title": "...", "description": ""}]}.'
            )

        return f"{instruction}\n\nNOTES:\n{notes}\n\nJSON:"

    def extract(self, text: str, llm_tier: str = "large") -> list[Task]:
        """
        Extract tasks from text. Safe fallback: return [] on any parsing errors.
        """
        logger.info("TaskExtractor: extracting tasks (tier=%s)", llm_tier)

        prompt = self._build_prompt(text, llm_tier)
        raw = self.llm_client.complete(prompt)
        if not raw:
            logger.warning("TaskExtractor: empty LLM response")
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("TaskExtractor: invalid JSON from LLM")
            return []

        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            logger.warning("TaskExtractor: JSON 'tasks' is not a list")
            return []

        out: list[Task] = []
        for t in tasks:
            if not isinstance(t, dict) or not t.get("title"):
                continue

            t = dict(t)
            if t.get("description") is None:
                t["description"] = ""

            try:
                out.append(Task(**t))
            except Exception:
                # If one task is malformed, skip it instead of failing the whole extraction
                continue

        return out
