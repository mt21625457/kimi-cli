from __future__ import annotations

import asyncio
import json

import pytest

from kimi_http.runner import RunManager, new_handle
from kimi_http.server import API_PREFIX, create_app


class DummyExecutor:
    async def start_run(self, request, handle, manager: RunManager):
        await handle.publish(
            "run_started",
            {"work_dir": str(request.work_dir)},
        )
        await handle.publish("run_completed", {"status": "finished"})
        await handle.close()
        manager.remove(handle.id)


@pytest.mark.asyncio
async def test_health_endpoint():
    app = create_app(run_executor=DummyExecutor())
    test_client = app.test_client()
    response = await test_client.get(f"{API_PREFIX}/health")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["status"] == "ok"


@pytest.mark.asyncio
async def test_run_endpoint_streams_events(tmp_path):
    app = create_app(run_executor=DummyExecutor())
    client = app.test_client()

    response = await client.post(
        f"{API_PREFIX}/runs",
        json={"command": "echo hi", "work_dir": str(tmp_path)},
    )
    assert response.status_code == 200
    body = (await response.get_data()).decode("utf-8").strip().splitlines()
    events = [json.loads(line) for line in body]
    assert events[0]["type"] == "run_started"
    assert events[-1]["payload"]["status"] == "finished"


@pytest.mark.asyncio
async def test_cancel_endpoint(tmp_path):
    app = create_app(run_executor=DummyExecutor())
    client = app.test_client()
    manager: RunManager = app.config["run_manager"]

    handle = new_handle()
    manager.register(handle)
    try:
        response = await client.post(f"{API_PREFIX}/runs/{handle.id}/cancel")
        assert response.status_code == 200
        payload = await response.get_json()
        assert payload["status"] == "cancelling"
    finally:
        manager.remove(handle.id)


@pytest.mark.asyncio
async def test_run_endpoint_batch_mode(tmp_path):
    app = create_app(run_executor=DummyExecutor())
    client = app.test_client()

    response = await client.post(
        f"{API_PREFIX}/runs",
        json={"command": "echo hi", "work_dir": str(tmp_path), "stream": False},
    )
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["run_id"]
    assert payload["events"][0]["type"] == "run_started"
    assert payload["events"][-1]["payload"]["status"] == "finished"
