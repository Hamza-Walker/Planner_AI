from llm.llm_client import LLMClient


class TaskExtractor:

    def extract(self, text: str, llm_tier: str = "large"):
        llm = LLMClient()
        tasks = llm.extract_tasks(text, model_tier=llm_tier)
        return tasks
