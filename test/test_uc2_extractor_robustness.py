import pytest
from extraction.task_extractor import TaskExtractor
from llm.llm_client import LLMClient

def test_uc2_garbage_output(fake_provider_factory):
    provider = fake_provider_factory("THIS IS NOT JSON AT ALL")
    extractor = TaskExtractor(llm_client=LLMClient(provider=provider))
    tasks = extractor.extract("random text")
    assert tasks == []

def test_uc2_null_description(fake_provider_factory):
    provider = fake_provider_factory(
        '{"tasks":[{"title":"Dentist","description":null,"estimated_duration_min":30}]}'
    )
    extractor = TaskExtractor(llm_client=LLMClient(provider=provider))
    tasks = extractor.extract("Dentist")
    assert len(tasks) == 1
    assert tasks[0].description == ""