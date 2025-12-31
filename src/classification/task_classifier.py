from llm.llm_client import LLMClient
from storage.preferences_store import PreferencesStore


class TaskClassifier:

    def classify(self, tasks: list, llm_tier: str = "large"):
        prefs = PreferencesStore().load()
        llm = LLMClient()
        classified_tasks = llm.classify_tasks(tasks, prefs, model_tier=llm_tier)
        return classified_tasks
