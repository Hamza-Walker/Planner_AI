from llm.llm_client import LLMClient


class TaskExtractor:

    def extract(self, text: str):
        llm = LLMClient()
        tasks = llm.extract_tasks(text)
        return tasks
