import os
import importlib
from fastapi.testclient import TestClient
from planner_ai.models import Task


import importlib
from planner_ai.models import Task


def test_step1_backendapi_contract(monkeypatch) -> None:
    backend_mod = importlib.import_module("api.backend")

    class FakeExtractor:
        def extract(self, notes: str, llm_tier: str = "large"):
            return [Task(title="T1", description="")]

    class FakeClassifier:
        def classify(self, tasks, llm_tier: str = "large"):
            out = []
            for t in tasks:
                task = t if isinstance(t, Task) else Task(**t)
                out.append(task.model_copy(update={"category": "other", "priority": 3}))
            return out

    class FakeScheduleBlock:
        def __init__(self, title: str, start: str, end: str):
            self.title = title
            self.start = start
            self.end = end

        def model_dump(self):
            return {"title": self.title, "start": self.start, "end": self.end}

    class FakeScheduler:
        def schedule(self, tasks):
            return [FakeScheduleBlock("T1", "09:00", "09:15")]

    class FakeCalendar:
        def sync(self, scheduled_tasks):
            return None

    monkeypatch.setattr(backend_mod, "TaskExtractor", FakeExtractor, raising=True)
    monkeypatch.setattr(backend_mod, "TaskClassifier", FakeClassifier, raising=True)
    monkeypatch.setattr(backend_mod, "Scheduler", FakeScheduler, raising=True)
    monkeypatch.setattr(backend_mod, "CalendarIntegration", FakeCalendar, raising=True)

    backend = backend_mod.BackendAPI()
    result = backend.submit_notes("note text", llm_tier="fast")

    assert isinstance(result, dict)
    assert set(result.keys()) >= {"tasks", "schedule", "tasks_processed"}
    assert isinstance(result["tasks"], list)
    assert isinstance(result["schedule"], list)
    assert isinstance(result["tasks_processed"], int)


def test_step2_fastapi_notes_response_schema(monkeypatch) -> None:
    """
    Step 2: /notes endpoint returns stable schema and stores recent tasks/schedule.
    We patch backend.submit_notes() to keep test deterministic.
    """
    os.environ["ENERGY_STATUS_URL"] = ""

    main_mod = importlib.import_module("api.main")

    def fake_submit_notes(notes: str, llm_tier: str = "large") -> dict:
        return {
            "tasks": [{"title": "Buy milk", "description": "", "category": "other", "priority": 3}],
            "schedule": [{"title": "Buy milk", "start": "09:00", "end": "09:15"}],
            "tasks_processed": 1,
        }

    monkeypatch.setattr(main_mod.backend, "submit_notes", fake_submit_notes, raising=True)

    client = TestClient(main_mod.app)

    r = client.post("/notes", json={"notes": "Buy milk"})
    assert r.status_code == 200
    body = r.json()

    assert body["status"] in {"processed", "queued"}
    assert "tasks" in body
    assert "schedule" in body
    assert "tasks_processed" in body
    assert isinstance(body["tasks"], list)
    assert isinstance(body["schedule"], list)
    assert isinstance(body["tasks_processed"], int)

    # If processed, the app should store the results.
    if body["status"] == "processed":
        # recent tasks endpoint
        t = client.get("/tasks")
        assert t.status_code == 200
        assert t.json()["total"] >= 1

        # today's schedule
        s = client.get("/schedule")
        assert s.status_code == 200
        assert isinstance(s.json()["schedule"], list)


def test_step3_llm_tier_propagation_and_effect(monkeypatch) -> None:
    """
    Step 3: Ensure llm_tier is propagated into the pipeline,
    and that 'eco' tier has a real behavioral effect (TaskClassifier eco fallback).
    This test patches extractor + llm client classify method so no network is used.
    """
    extraction_mod = importlib.import_module("extraction.task_extractor")
    classifier_mod = importlib.import_module("classification.task_classifier")

    # Capture the prompt passed into LLMClient.complete in extractor
    seen = {"prompt": None}

    class FakeLLM:
        def complete(self, prompt: str):
            seen["prompt"] = prompt
            # Return strict JSON as expected by extractor
            return '{"tasks":[{"title":"T1","description":""}]}'

        def classify_tasks(self, payload):
            # For non-eco, return something classified
            return [{"title": "T1", "category": "work", "priority": 5}]

    # Patch extractor LLM client
    extractor = extraction_mod.TaskExtractor(llm_client=FakeLLM())
    tasks = extractor.extract("do something", llm_tier="eco")

    assert tasks and tasks[0].title == "T1"
    assert seen["prompt"] is not None
    # Ensure tier prompt actually changes content (at least mentions minimal/conservative).
    assert "minimal" in seen["prompt"].lower() or "conservative" in seen["prompt"].lower()

    # Patch classifier LLM client and ensure eco does NOT call classify_tasks in a required way
    class EcoLLM(FakeLLM):
        def classify_tasks(self, payload):
            raise AssertionError("eco tier should not call LLM classify_tasks")

    classifier = classifier_mod.TaskClassifier(llm_client=EcoLLM())
    out = classifier.classify(tasks, llm_tier="eco")

    assert out and out[0].category is not None
    assert out[0].priority is not None
