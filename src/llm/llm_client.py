import os
from typing import Any


class LLMClient:
    """LLM client stub with a sustainability-oriented 'model tier' knob.

    This is intentionally provider-agnostic for now.
    Configure your concrete provider in a later step.
    """

    def _select_model_name(self, model_tier: str) -> str:
        if model_tier == "small":
            return os.getenv("LLM_MODEL_SMALL", "small")
        return os.getenv("LLM_MODEL_LARGE", "large")

    def extract_tasks(self, text: str, model_tier: str = "large") -> list[dict[str, Any]]:
        _model = self._select_model_name(model_tier)
        # TODO: call external LLM API; for now return empty result.
        return []

    def classify_tasks(
        self,
        tasks: list,
        preferences: dict,
        model_tier: str = "large",
    ) -> list:
        _model = self._select_model_name(model_tier)
        # TODO: call external LLM API; for now return tasks unchanged.
        return tasks
