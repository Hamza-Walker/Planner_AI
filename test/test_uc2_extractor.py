from extraction.task_extractor import TaskExtractor
from llm.llm_client import LLMClient

def test_uc2(fake_provider_factory):
    provider = fake_provider_factory(
        '{"tasks":[{"title":"Book dentist","estimated_duration_min":30,"deadline":null}]}'
    )
    extractor = TaskExtractor(llm_client=LLMClient(provider=provider))
    tasks = extractor.extract("Book dentist")
    assert len(tasks) == 1