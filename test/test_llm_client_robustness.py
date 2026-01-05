from llm.llm_client import LLMClient

def test_llm_extra_text_around_json(fake_provider_factory):
    provider = fake_provider_factory(
        'Sure! Here is the result: {"tasks":[{"title":"Call mom","estimated_duration_min":10}]} Thanks.'
    )
    client = LLMClient(provider=provider)
    out = client.complete("Call mom")
    assert "tasks" in out

def test_llm_invalid_json_fallback(fake_provider_factory):
    provider = fake_provider_factory("INVALID OUTPUT")
    client = LLMClient(provider=provider)
    out = client.complete("Anything")
    assert out == '{"tasks": []}' or "tasks" in out