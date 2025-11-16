from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from kosong.message import ContentPart, TextPart, ThinkPart, ToolCall, ToolCallPart
from kosong.tooling import ToolOk, ToolResult
from rich.table import Table
from rich.text import Text

from kimi_cli.soul import (
    LLMNotSet,
    LLMNotSupported,
    MaxStepsReached,
    RunCancelled,
    Soul,
    run_soul,
)
from kimi_cli.ui.shell.console import console
from kimi_cli.utils.logging import logger
from kimi_cli.wire import WireUISide
from kimi_cli.wire.message import (
    ApprovalRequest,
    ApprovalResponse,
    CompactionBegin,
    CompactionEnd,
    StatusUpdate,
    StepBegin,
    StepInterrupted,
    SubagentEvent,
    WireMessage,
)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ShellTask:
    id: int
    command_text: str
    user_input: str | Sequence[ContentPart]
    thinking: bool | None
    created_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.QUEUED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    logs: list[str] = field(default_factory=list)
    pending_approvals: set[str] = field(default_factory=set)

    def short_command(self, limit: int = 60) -> str:
        if len(self.command_text) <= limit:
            return self.command_text
        return self.command_text[: limit - 1] + "…"


@dataclass(slots=True)
class ApprovalEntry:
    task_id: int
    request: ApprovalRequest


class TaskStateStore:
    """In-memory store for shell tasks and approvals."""

    def __init__(self):
        self._tasks: dict[int, ShellTask] = {}
        self._approvals: dict[str, ApprovalEntry] = {}
        self._next_id = 1

    def create_task(
        self,
        *,
        command_text: str,
        user_input: str | Sequence[ContentPart],
        thinking: bool | None,
    ) -> ShellTask:
        task = ShellTask(
            id=self._next_id,
            command_text=command_text,
            user_input=user_input,
            thinking=thinking,
        )
        self._next_id += 1
        self._tasks[task.id] = task
        self._log(task.id, f"Queued `{command_text}`")
        return task

    def tasks(self) -> list[ShellTask]:
        return list(self._tasks.values())

    def get(self, task_id: int) -> ShellTask | None:
        return self._tasks.get(task_id)

    def mark_running(self, task_id: int) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            self._log(task_id, "Started")

    def mark_waiting_approval(self, task_id: int, request: ApprovalRequest) -> None:
        task = self.get(task_id)
        if task is None:
            request.resolve(ApprovalResponse.REJECT)
            return
        task.status = TaskStatus.WAITING_APPROVAL
        task.pending_approvals.add(request.id)
        self._approvals[request.id] = ApprovalEntry(task_id=task_id, request=request)
        self._log(
            task_id,
            (
                "Approval required: "
                f"{request.sender} wants to {request.action} ({request.description}). "
                f"Respond with `/approve {request.id}`, `/approve-session {request.id}` "
                f"或 `/reject {request.id}`."
            ),
            style="yellow",
        )

    def resolve_approval(self, approval_id: str, response: ApprovalResponse) -> str:
        entry = self._approvals.pop(approval_id, None)
        if entry is None:
            return "未找到匹配的审批请求。"
        task = self.get(entry.task_id)
        if task:
            task.pending_approvals.discard(approval_id)
            if not task.pending_approvals and task.status == TaskStatus.WAITING_APPROVAL:
                task.status = TaskStatus.RUNNING
        entry.request.resolve(response)
        action = {
            ApprovalResponse.APPROVE: "已批准",
            ApprovalResponse.APPROVE_FOR_SESSION: "已在本会话内自动批准",
            ApprovalResponse.REJECT: "已拒绝",
        }[response]
        self._log(entry.task_id, f"{action}审批请求 {approval_id}", style="cyan")
        return f"{action}。"

    def mark_succeeded(self, task_id: int) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.SUCCEEDED
            task.finished_at = datetime.now()
            self._log(task_id, "完成", style="green")

    def mark_failed(self, task_id: int, reason: str) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.FAILED
            task.finished_at = datetime.now()
            self._log(task_id, f"失败：{reason}", style="red")

    def mark_cancelling(self, task_id: int) -> None:
        if task := self.get(task_id):
            if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                return
            task.status = TaskStatus.CANCELLING
            self._log(task_id, "正在尝试取消", style="yellow")

    def mark_cancelled(self, task_id: int, reason: str | None = None) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.CANCELLED
            task.finished_at = datetime.now()
            msg = "已取消" + (f"：{reason}" if reason else "")
            self._log(task_id, msg, style="yellow")

    def drop_pending_approvals(self, task_id: int, response: ApprovalResponse) -> None:
        task = self.get(task_id)
        if task is None:
            return
        for approval_id in list(task.pending_approvals):
            self.resolve_approval(approval_id, response)

    def approvals(self) -> list[ApprovalEntry]:
        return list(self._approvals.values())

    def append_log(self, task_id: int, message: str, *, style: str | None = None) -> None:
        if task := self.get(task_id):
            task.logs.append(message)
            if len(task.logs) > 20:
                task.logs.pop(0)
        self._log(task_id, message, style=style)

    def build_table(self) -> Table:
        table = Table(title="Shell Tasks", show_lines=False, box=None)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("状态", style="magenta")
        table.add_column("命令")
        table.add_column("更新时间", style="grey50")
        for task in sorted(self._tasks.values(), key=lambda t: t.id):
            updated = task.finished_at or task.started_at or task.created_at
            table.add_row(
                str(task.id),
                task.status.value,
                task.short_command(),
                updated.strftime("%H:%M:%S"),
            )
        if not self._tasks:
            table.add_row("-", "-", "暂无任务", "-")
        return table

    def _log(self, task_id: int, message: str, *, style: str | None = None) -> None:
        prefix = Text(f"[任务 {task_id}] ", style="cyan")
        body = Text(message, style=style or "grey70")
        console.print(prefix + body)


class ShellTaskManager:
    """Manage background execution of soul commands in Shell UI."""

    def __init__(self, soul: Soul):
        self._soul = soul
        self._store = TaskStateStore()
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._executor_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._executor_task is None:
            self._executor_task = asyncio.create_task(self._executor_loop())

    async def shutdown(self) -> None:
        if self._executor_task:
            self._executor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._executor_task
            self._executor_task = None

    def submit(
        self,
        *,
        command_text: str,
        user_input: str | Sequence[ContentPart],
        thinking: bool | None,
    ) -> ShellTask:
        task = self._store.create_task(
            command_text=command_text,
            user_input=user_input,
            thinking=thinking,
        )
        self._queue.put_nowait(task.id)
        return task

    def list_tasks(self) -> Table:
        return self._store.build_table()

    def list_approvals(self) -> list[ApprovalEntry]:
        return self._store.approvals()

    def resolve_approval(self, approval_id: str, response: ApprovalResponse) -> str:
        return self._store.resolve_approval(approval_id, response)

    def cancel_task(self, task_id: int) -> str:
        task = self._store.get(task_id)
        if task is None:
            return "任务不存在。"
        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return "任务已经结束。"
        if task.status == TaskStatus.QUEUED:
            task.cancel_event.set()
            self._store.mark_cancelled(task_id, "尚未执行，立即停止。")
            task.pending_approvals.clear()
            return "已取消排队中的任务。"
        self._store.mark_cancelling(task_id)
        self._store.drop_pending_approvals(task_id, ApprovalResponse.REJECT)
        task.cancel_event.set()
        return "已请求取消任务。"

    async def _executor_loop(self) -> None:
        while True:
            task_id = await self._queue.get()
            task = self._store.get(task_id)
            if task is None or task.status == TaskStatus.CANCELLED:
                continue
            await self._run_task(task)

    async def _run_task(self, task: ShellTask) -> None:
        cancel_event = task.cancel_event
        self._store.mark_running(task.id)
        try:
            if hasattr(self._soul, "set_thinking"):
                from kimi_cli.soul.kimisoul import KimiSoul

                if isinstance(self._soul, KimiSoul) and task.thinking is not None:
                    self._soul.set_thinking(task.thinking)
            await run_soul(
                self._soul,
                task.user_input,
                lambda wire: _TaskObserver(self._store, task.id).observe(wire),
                cancel_event,
            )
            self._store.mark_succeeded(task.id)
        except LLMNotSet:
            self._store.mark_failed(task.id, "未配置 LLM，使用 /setup 进行配置。")
        except LLMNotSupported as e:
            self._store.mark_failed(
                task.id,
                f"LLM 不支持所需能力：{', '.join(e.capabilities)}",
            )
        except MaxStepsReached as e:
            self._store.mark_failed(task.id, f"达到最大步数 {e.n_steps}")
        except RunCancelled:
            self._store.mark_cancelled(task.id, "用户中断")
        except asyncio.CancelledError:
            self._store.mark_cancelled(task.id, "Shell 退出")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("任务执行失败:")
            self._store.mark_failed(task.id, f"未知错误：{exc}")


class _TaskObserver:
    """Consume wire events and log them to the task store."""

    def __init__(self, store: TaskStateStore, task_id: int):
        self._store = store
        self._task_id = task_id
        self._tool_names: dict[str, str] = {}

    async def observe(self, wire: WireUISide) -> None:
        while True:
            try:
                msg = await wire.receive()
            except asyncio.QueueShutDown:
                return
            self._handle_message(msg)

    def _handle_message(self, msg: WireMessage) -> None:
        match msg:
            case StepBegin():
                self._store.append_log(self._task_id, f"Step {msg.n} 开始")
            case StepInterrupted():
                self._store.append_log(self._task_id, "Step 中断", style="yellow")
            case CompactionBegin():
                self._store.append_log(self._task_id, "开始压缩上下文…", style="yellow")
            case CompactionEnd():
                self._store.append_log(self._task_id, "上下文压缩完成", style="yellow")
            case StatusUpdate(status=status):
                self._store.append_log(
                    self._task_id,
                    f"上下文占用 {status.context_usage:.1%}",
                    style="grey50",
                )
            case ContentPart() as part:
                snippet = self._content_snippet(part)
                if snippet:
                    self._store.append_log(self._task_id, snippet)
            case ToolCall() as call:
                self._tool_names[call.id] = call.function.name
                self._store.append_log(self._task_id, f"调用工具 {call.function.name}")
            case ToolCallPart():
                # streaming tool arguments; ignore
                return
            case ToolResult() as result:
                name = self._tool_names.get(result.tool_call_id, result.tool_call_id)
                ok = isinstance(result.result, ToolOk)
                brief = (result.result.brief or result.result.message or "").strip()
                if brief and len(brief) > 80:
                    brief = brief[:77] + "…"
                message = f"工具 {name} {'成功' if ok else '失败'}"
                if brief:
                    message += f"：{brief}"
                self._store.append_log(
                    self._task_id,
                    message,
                    style="green" if ok else "red",
                )
            case ApprovalRequest():
                self._store.mark_waiting_approval(self._task_id, msg)
            case SubagentEvent(event=sub_event):
                self._store.append_log(
                    self._task_id,
                    f"子代理事件 {type(sub_event).__name__}",
                    style="grey50",
                )
            case _:
                self._store.append_log(self._task_id, f"收到事件 {type(msg).__name__}")

    @staticmethod
    def _content_snippet(part: ContentPart) -> str | None:
        if isinstance(part, TextPart):
            text = part.text.strip()
            if not text:
                return None
            return text if len(text) <= 120 else text[:117] + "…"
        if isinstance(part, ThinkPart):
            text = part.text.strip()
            if not text:
                return None
            prefix = "思考"
            body = text if len(text) <= 100 else text[:97] + "…"
            return f"[{prefix}] {body}"
        return None
