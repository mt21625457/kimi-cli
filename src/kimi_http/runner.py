from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from loguru import logger
from kosong.chat_provider import ChatProviderError

from kimi_cli.soul import (
    LLMNotSet,
    LLMNotSupported,
    MaxStepsReached,
    RunCancelled,
    run_soul,
)
from kimi_cli.wire import WireUISide
from kimi_cli.wire.message import (
    ApprovalRequest,
    ApprovalResponse,
    serialize_approval_request,
    serialize_event,
)

from .models import RunRequest
from .runtime import RuntimeFactory


def _encode_event(run_id: str, event_type: str, payload: Any) -> bytes:
    document = {
        "run_id": run_id,
        "type": event_type,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    return (json.dumps(document, ensure_ascii=False) + "\n").encode("utf-8")


@dataclass(slots=True)
class RunHandle:
    id: str
    queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None

    async def publish(self, event_type: str, payload: Any) -> None:
        await self.queue.put(_encode_event(self.id, event_type, payload))

    async def close(self) -> None:
        await self.queue.put(None)

    def stream(self) -> AsyncIterator[bytes]:
        async def _generator() -> AsyncIterator[bytes]:
            while True:
                chunk = await self.queue.get()
                if chunk is None:
                    break
                yield chunk

        return _generator()


class RunManager:
    """Track live runs for cancellation."""

    def __init__(self):
        self._handles: dict[str, RunHandle] = {}

    def register(self, handle: RunHandle) -> None:
        self._handles[handle.id] = handle

    def get(self, run_id: str) -> RunHandle | None:
        return self._handles.get(run_id)

    def remove(self, run_id: str) -> None:
        self._handles.pop(run_id, None)

    async def cancel(self, run_id: str) -> bool:
        handle = self._handles.get(run_id)
        if handle is None:
            return False
        handle.cancel_event.set()
        return True


class RunExecutor:
    """Create and run soul instances for HTTP requests."""

    def __init__(self, runtime_factory: RuntimeFactory | None = None):
        self._factory = runtime_factory or RuntimeFactory()

    async def start_run(self, request: RunRequest, handle: RunHandle, manager: RunManager) -> None:
        try:
            artifacts = await self._factory.create(request)
        except Exception as exc:  # pragma: no cover - exercised in integration tests
            logger.exception("Failed to create runtime:")
            await handle.publish(
                "error",
                {
                    "message": "failed to prepare runtime",
                    "details": str(exc),
                },
            )
            await handle.publish("run_completed", {"status": "error"})
            await handle.close()
            manager.remove(handle.id)
            return

        await handle.publish(
            "thread.started",
            {
                "thread_id": handle.id,
                "work_dir": str(request.work_dir),
                "agent_file": str(artifacts.agent_file),
                "session_id": artifacts.session.id,
                "model_name": artifacts.soul.model_name,
                "env_overrides": artifacts.env_overrides,
            },
        )
        await handle.publish("turn.started", {})

        transformer = _WireEventAggregator(handle)

        status_payload: dict[str, Any] = {"status": "finished"}

        try:
            await run_soul(
                artifacts.soul,
                request.command,
                lambda wire: self._ui_loop(wire, handle, transformer),
                handle.cancel_event,
            )
        except LLMNotSet:
            await self._publish_error(handle, "LLM is not configured")
            status_payload = {"status": "error"}
        except LLMNotSupported as exc:
            await self._publish_error(handle, str(exc))
            status_payload = {"status": "error"}
        except ChatProviderError as exc:
            await self._publish_error(handle, f"LLM provider error: {exc}")
            status_payload = {"status": "error"}
        except MaxStepsReached as exc:
            status_payload = {"status": "max_steps_reached", "steps": exc.n_steps}
        except RunCancelled:
            status_payload = {"status": "cancelled"}
        except Exception as exc:  # pragma: no cover - logged for observability
            logger.exception("Run execution failed:")
            await self._publish_error(handle, f"run failed: {exc}")
            status_payload = {"status": "error"}
        finally:
            await transformer.flush()
            await handle.publish("turn.completed", status_payload)
            await handle.close()
            manager.remove(handle.id)

    async def _ui_loop(
        self,
        wire: WireUISide,
        handle: RunHandle,
        transformer: _WireEventAggregator,
    ) -> None:
        while True:
            try:
                message = await wire.receive()
            except asyncio.QueueShutDown:
                break
            if isinstance(message, ApprovalRequest):
                await handle.publish(
                    "approval_request",
                    serialize_approval_request(message),
                )
                message.resolve(ApprovalResponse.APPROVE)
                await handle.publish(
                    "approval_response",
                    {"id": message.id, "decision": ApprovalResponse.APPROVE.value},
                )
            else:
                await transformer.handle(serialize_event(message))

        await transformer.flush()

    async def _publish_error(self, handle: RunHandle, message: str) -> None:
        await handle.publish("error", {"message": message})


def new_handle() -> RunHandle:
    return RunHandle(id=str(uuid.uuid4()))


class _WireEventAggregator:
    def __init__(self, handle: RunHandle):
        self._handle = handle
        self._buffer: list[str] = []

    async def handle(self, event: dict[str, Any]) -> None:
        if event.get("type") == "content_part" and event.get("payload", {}).get("type") == "text":
            text = event["payload"].get("text", "")
            if text:
                self._buffer.append(text)
            return

        await self.flush()
        await self._handle.publish("wire_event", event)

    async def flush(self) -> None:
        if not self._buffer:
            return
        text = "".join(self._buffer).strip()
        if text:
            await self._handle.publish(
                "wire_event",
                {"type": "content_part", "payload": {"type": "text", "text": text}},
            )
        self._buffer.clear()
