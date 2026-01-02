from planner_ai.models import Task
from classification.task_classifier import TaskClassifier
from llm.llm_client import LLMClient

def test_uc3(fake_provider_factory):
    provider = fake_provider_factory(
        '{"tasks":[{"title":"Task","category":"work","priority":1}]}'
    )
    classifier = TaskClassifier(llm_client=LLMClient(provider=provider))
    out = classifier.classify([Task(title="Task")])
    assert out[0].priority == 1