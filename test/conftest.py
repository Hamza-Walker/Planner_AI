import pytest

class FakeProvider:
    def __init__(self, response_text: str):
        self._response_text = response_text

    def generate(self, *, system: str, user: str) -> str:
        return self._response_text

@pytest.fixture
def fake_provider_factory():
    def _make(response_text: str):
        return FakeProvider(response_text)
    return _make