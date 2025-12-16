from llm.llm_client import LLMClient
from storage.preferences_store import PreferencesStore


class TaskClassifier:

    def classify(self, tasks: list):
        prefs = PreferencesStore().load()
        llm = LLMClient()
        classified_tasks = llm.classify_tasks(tasks, prefs)
        return classified_tasks
