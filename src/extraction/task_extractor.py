import json
from planner_ai.models import Task
from llm.llm_client import LLMClient

class TaskExtractor:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or LLMClient()

    def extract(self, text: str) -> list[Task]:
        raw = self.llm_client.complete(text)
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            return []

        out: list[Task] = []
        for t in tasks:
            if not isinstance(t, dict) or not t.get("title"):
                continue

            t = dict(t)
            if t.get("description") is None:
                t["description"] = ""

            out.append(Task(**t))

        return out
