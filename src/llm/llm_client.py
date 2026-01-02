from __future__ import annotations
import json
import os
from typing import Any, Optional

from pydantic import ValidationError

from llm.schemas import (
    TaskExtractionResult,
    TaskClassificationResult,
)
from llm.providers.openai_provider import OpenAIProvider
from llm.providers.ollama_provider import OllamaProvider
from llm.providers.base import LLMProvider


JSON_ONLY_RULES = """
Return ONLY valid JSON. No markdown. No commentary. No code fences.
If unsure, return {"tasks": []}.
""".strip()


def _extract_json(text: str) -> str:
    """
    Robust-ish: tries to extract a JSON object from model output.
    Works even if model adds some stray text.
    """
    text = text.strip()

    # already JSON
    if text.startswith("{") and text.endswith("}"):
        return text

    # try to find first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    # give up
    return "{}"


class LLMClient:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or self._build_provider()

    def _build_provider(self) -> LLMProvider:
        name = os.getenv("LLM_PROVIDER", "openai").strip().lower()
        if name == "openai":
            return OpenAIProvider()
        if name == "ollama":
            return OllamaProvider()

        # fallback "no-llm" mode
        raise RuntimeError(f"Unknown LLM_PROVIDER: {name}")

    # ---------- UC2: Extract Tasks ----------

    def extract_tasks(self, note_text: str) -> list[dict[str, Any]]:
        """
        Returns list of task dicts compatible with Task(**dict) in your extractor.
        (We return dicts here to keep your existing UC2 stub integration easy.)
        """
        system = f"You extract actionable tasks from notes. {JSON_ONLY_RULES}"

        user = f"""
Extract tasks from this note.

Return JSON with schema:
{{
  "tasks": [
    {{
      "title": "string",
      "description": "string | null",
      "estimated_duration_min": 30,
      "deadline": "ISO-8601 datetime | null"
    }}
  ]
}}

NOTE:
- If duration unknown, set 30.
- deadline can be null.
- title must be concise.
- Only include actionable tasks.

NOTE TEXT:
{note_text}
""".strip()

        try:
            raw = self.provider.generate(system=system, user=user)
            json_text = _extract_json(raw)
            parsed = TaskExtractionResult.model_validate_json(json_text)
            return [t.model_dump() for t in parsed.tasks]
        except (ValidationError, json.JSONDecodeError, Exception):
            # safe fallback: no tasks
            return []

    # ---------- UC3: Classify & Prioritize ----------

    def classify_tasks(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Input: task dicts (title, description, duration, deadline)
        Output: task dicts + category + priority
        """
        system = f"You classify and prioritize tasks. {JSON_ONLY_RULES}"

        user = f"""
Classify and prioritize these tasks.

Return JSON with schema:
{{
  "tasks": [
    {{
      "title": "string",
      "description": "string | null",
      "estimated_duration_min": 30,
      "deadline": "ISO-8601 datetime | null",
      "category": "work|personal|health|learning|other",
      "priority": 1
    }}
  ]
}}

Rules:
- priority: 1 (highest) .. 5 (lowest)
- if unclear, category="other", priority=3

TASKS:
{json.dumps(tasks, ensure_ascii=False)}
""".strip()

        try:
            raw = self.provider.generate(system=system, user=user)
            json_text = _extract_json(raw)
            parsed = TaskClassificationResult.model_validate_json(json_text)
            return [t.model_dump() for t in parsed.tasks]
        except (ValidationError, json.JSONDecodeError, Exception):
            # fallback: return unchanged, with defaults if missing
            out: list[dict[str, Any]] = []
            for t in tasks:
                t = dict(t)
                t.setdefault("category", "other")
                t.setdefault("priority", 3)
                out.append(t)
            return out
