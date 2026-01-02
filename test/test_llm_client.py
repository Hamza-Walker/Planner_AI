from llm.llm_client import LLMClient

def test_extract_tasks(fake_provider_factory):
    provider = fake_provider_factory(
        '{"tasks":[{"title":"Send invoice","estimated_duration_min":20,"deadline":null}]}'
    )
    client = LLMClient(provider=provider)
    tasks = client.extract_tasks("Send invoice")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Send invoice"