import os
import importlib

from fastapi.testclient import TestClient


def _import_app():
    # Import lazily so environment variables (if any) can be set before import.
    mod = importlib.import_module("api.main")
    return mod


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    mod = _import_app()
    client = TestClient(mod.app)

    r = client.get("/metrics")
    assert r.status_code == 200
    # Prometheus text exposition format content-type
    assert "text/plain" in r.headers.get("content-type", "")
    body = r.text
    # Key metric names should appear
    assert "planner_requests_total" in body
    assert "planner_request_latency_seconds" in body
    assert "planner_queue_depth" in body


def test_notes_increments_request_counter(monkeypatch) -> None:
    # Ensure energy endpoint is disabled so policy is evaluated with status=None
    os.environ["ENERGY_STATUS_URL"] = ""

    mod = _import_app()

    # Monkeypatch backend to avoid any LLM/network calls and keep test deterministic.
    def fake_submit_notes(notes: str, llm_tier: str = "large") -> dict:
        return {
            "tasks": [{"title": "Buy milk", "description": "", "category": "other", "priority": 3}],
            "schedule": [{"title": "Buy milk", "start": "09:00", "end": "09:15"}],
            "tasks_processed": 1,
        }

    monkeypatch.setattr(mod.backend, "submit_notes", fake_submit_notes, raising=True)

    client = TestClient(mod.app)

    r = client.post("/notes", json={"notes": "Buy milk"})
    assert r.status_code == 200
    assert r.json().get("status") in {"processed", "queued"}

    m = client.get("/metrics")
    assert m.status_code == 200

    body = m.text
    assert "planner_requests_total" in body

    # Look for a concrete sample line for /notes (processed or queued).
    # We avoid parsing because Prometheus text parsers can be fragile across environments.
    lines = body.splitlines()
    found = any(
        line.startswith('planner_requests_total{endpoint="/notes",status="processed"}')
        or line.startswith('planner_requests_total{endpoint="/notes",status="queued"}')
        for line in lines
    )
    assert found, "Expected planner_requests_total sample line for /notes"


def test_metrics_queue_depth_matches_queue_endpoint() -> None:
    os.environ["ENERGY_STATUS_URL"] = ""

    mod = _import_app()
    client = TestClient(mod.app)

    q = client.get("/queue")
    assert q.status_code == 200
    queue_size = q.json()["queue_size"]

    m = client.get("/metrics")
    assert m.status_code == 200

    # Find the gauge line directly:
    # planner_queue_depth <number>
    depth = None
    for line in m.text.splitlines():
        if line.startswith("planner_queue_depth "):
            depth = line.split(" ", 1)[1].strip()
            break

    assert depth is not None, "planner_queue_depth metric not found"
    assert int(float(depth)) == int(queue_size)
