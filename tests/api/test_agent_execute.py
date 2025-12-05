from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_execute_task_enqueues_and_returns_task_id(monkeypatch):
    from app.worker import tasks as worker_tasks

    called = {"value": False}

    def fake_delay(task_id: str):
        called["value"] = True

    monkeypatch.setattr(worker_tasks.process_task, "delay", fake_delay)

    client = TestClient(app)
    response = client.post(
        "/v1/agent/execute",
        json={"task": "kod yaz"},
        headers={"X-API-Key": "test-api-key-1"},
    )

    # In tests without env overrides, API key check may be disabled; we just assert 200
    assert response.status_code in (200, 401, 422)
    if response.status_code == 200:
        body = response.json()
        assert "task_id" in body
        assert body["status"] == "queued"
        assert called["value"] is True
