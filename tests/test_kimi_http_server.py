from __future__ import annotations

import asyncio
import json

import pytest

from kimi_http.runner import RunManager, new_handle
from kimi_http.server import API_PREFIX, create_app


class DummyExecutor:
    async def start_run(self, request, handle, manager: RunManager):
        await handle.publish(
            "thread.started",
            {"thread_id": handle.id, "work_dir": str(request.work_dir)},
        )
        await handle.publish("turn.started", {})
        await handle.publish(
            "wire_event",
            {"type": "content_part", "payload": {"type": "text", "text": "hi"}},
        )
        await handle.publish("turn.completed", {"status": "finished"})
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
async def test_run_endpoint_returns_json_payload(tmp_path):
    app = create_app(run_executor=DummyExecutor())
    client = app.test_client()

    response = await client.post(
        f"{API_PREFIX}/runs",
        json={
            "command": "echo hi",
            "work_dir": str(tmp_path),
            "stream": False,
            "include_events": True,
        },
    )
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["events"][0]["type"] == "thread.started"
    assert payload["events"][-1]["type"] == "turn.completed"
    assert payload["conversation"][0]["role"] == "user"
    if len(payload["conversation"]) > 1:
        assert payload["conversation"][1]["role"] == "assistant"


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
async def test_run_endpoint_streaming_ndjson(tmp_path):
    app = create_app(run_executor=DummyExecutor())
    client = app.test_client()

    response = await client.post(
        f"{API_PREFIX}/runs",
        json={"command": "echo hi", "work_dir": str(tmp_path)},
    )
    assert response.status_code == 200
    body = (await response.get_data()).decode("utf-8").strip().splitlines()
    events = [json.loads(line) for line in body]
    assert events[0]["type"] == "thread.started"
    assert events[-1]["type"] == "turn.completed"
    assistant_events = [
        e
        for e in events
        if e["type"] == "wire_event"
        and e["payload"].get("type") == "content_part"
        and e["payload"].get("payload", {}).get("type") == "text"
    ]
    assert assistant_events and assistant_events[0]["payload"]["payload"]["text"] == "hi"
