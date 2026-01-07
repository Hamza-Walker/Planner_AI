from __future__ import annotations
import json
import os
import re
from typing import Any, Optional

from pydantic import ValidationError

from llm.schemas import (
    TaskExtractionResult,
    TaskClassificationResult,
)
from llm.providers.openai_provider import OpenAIProvider
from llm.providers.ollama_provider import OllamaProvider
from llm.providers.mock_provider import MockProvider
from llm.providers.base import LLMProvider


import logging

logger = logging.getLogger(__name__)

JSON_ONLY_RULES = """
Return ONLY valid JSON. No markdown. No commentary. No code fences.
Do NOT use trailing commas. Do NOT use comments inside the JSON (like // or /* */).
If unsure, return {"tasks": []}.
""".strip()



def _extract_json(text: str) -> str:
    """
    Robust-ish: tries to extract a JSON object from model output.
    Works even if model adds some stray text.
    """
    # Remove C-style comments //...
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)

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
        self.large_model = os.getenv("LLM_MODEL_LARGE", "llama3.1").strip()
        self.small_model = os.getenv("LLM_MODEL_SMALL", "llama3.2:1b").strip()

    def _build_provider(self) -> LLMProvider:
        name = os.getenv("LLM_PROVIDER", "openai").strip().lower()
        if name == "openai":
            return OpenAIProvider()
        if name == "ollama":
            return OllamaProvider()

        # fallback "no-llm" mode
        raise RuntimeError(f"Unknown LLM_PROVIDER: {name}")

    
    def complete(self, note_text: str) -> str:
            """
            Backwards-compatible API used by unit tests and older components.
            Returns JSON string: {"tasks":[...]}.
            """
            tasks = self.extract_tasks(note_text)  # list[dict[str, Any]]
            return json.dumps({"tasks": tasks}, ensure_ascii=False)

    def extract_tasks(self, note_text: str, llm_tier: str = "large") -> list[dict[str, Any]]:
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
      "deadline": "ISO-8601 datetime | null",
      "fixed_time": "HH:MM | null"
    }}
  ]
}}

NOTE:
- If duration unknown, set 30.
- deadline can be null.
- fixed_time should be "HH:MM" (24h) if a specific time is mentioned (e.g. "at 21:30" -> "21:30").
- title must be concise.
- Only include actionable tasks.

NOTE TEXT:
{note_text}
""".strip()

        model_name = self.large_model if llm_tier == "large" else self.small_model
        # logger.info(f"Using model: {model_name} for tier: {llm_tier}")

        try:
            try:
                raw = self.provider.generate(system=system, user=user, model=model_name)
            except TypeError:
                # FakeProvider doesn't accept `model`
                raw = self.provider.generate(system=system, user=user)

            json_text = _extract_json(raw)
            parsed = TaskExtractionResult.model_validate_json(json_text)
            return [t.model_dump() for t in parsed.tasks]

        except (ValidationError, json.JSONDecodeError) as e:
            logger.error(f"Error extracting tasks: {e}. Raw output: {raw if 'raw' in locals() else 'N/A'}")
            return []


    def classify_tasks(self, tasks: list[dict[str, Any]], llm_tier: str = "large") -> list[dict[str, Any]]:
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
{json.dumps(tasks, ensure_ascii=False, default=str)}
""".strip()
        
        model_name = self.large_model if llm_tier == "large" else self.small_model

        try:
            try:
                raw = self.provider.generate(system=system, user=user, model=model_name)
            except TypeError:
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
