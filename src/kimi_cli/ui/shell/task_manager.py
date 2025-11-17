from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import os
import time
from datetime import datetime, timedelta
from enum import Enum

from kosong.message import ContentPart, TextPart, ThinkPart, ToolCall, ToolCallPart
from kosong.tooling import ToolOk, ToolResult
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kimi_cli.config import Config
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


class ColorMode(Enum):
    TRUECOLOR = "truecolor"
    LIMITED = "limited"
    MONO = "mono"


@dataclass(slots=True)
class ShellTask:
    id: int
    command_text: str
    user_input: str | Sequence[ContentPart]
    thinking: bool | None
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.QUEUED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    fade_deadline: datetime | None = None
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


ApprovalWaitCallback = Callable[["ApprovalEntry"], None]
ApprovalResolvedCallback = Callable[["ApprovalEntry", ApprovalResponse], None]


@dataclass(slots=True)
class TaskBannerSettings:
    visible_slots: int = 4
    refresh_interval: float = 1.0

    @classmethod
    def from_config(cls, config: Config | None) -> "TaskBannerSettings":
        if config is None:
            return cls()
        banner = config.shell.task_banner
        return cls(
            visible_slots=banner.visible_slots,
            refresh_interval=banner.refresh_interval,
        )


class TaskStateStore:
    """In-memory store for shell tasks and approvals."""

    def __init__(
        self,
        *,
        on_waiting_approval: ApprovalWaitCallback | None = None,
        on_approval_resolved: ApprovalResolvedCallback | None = None,
        on_tasks_changed: Callable[[], None] | None = None,
    ):
        self._tasks: dict[int, ShellTask] = {}
        self._approvals: dict[str, ApprovalEntry] = {}
        self._next_id = 1
        self._on_waiting_approval = on_waiting_approval
        self._on_approval_resolved = on_approval_resolved
        self._on_tasks_changed = on_tasks_changed

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
        self._log(task.id, f"Queued `{command_text}`", silent=True)
        self._notify_change()
        return task

    def tasks(self) -> list[ShellTask]:
        return list(self._tasks.values())

    def get(self, task_id: int) -> ShellTask | None:
        return self._tasks.get(task_id)

    def mark_running(self, task_id: int) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            task.last_active_at = task.started_at
            self._log(task_id, "Started", silent=True)
            self._notify_change()

    def mark_waiting_approval(self, task_id: int, request: ApprovalRequest) -> None:
        task = self.get(task_id)
        if task is None:
            request.resolve(ApprovalResponse.REJECT)
            return
        task.status = TaskStatus.WAITING_APPROVAL
        task.last_active_at = datetime.now()
        task.pending_approvals.add(request.id)
        entry = ApprovalEntry(task_id=task_id, request=request)
        self._approvals[request.id] = entry
        message_lines = [
            f"{request.sender} 想要 {request.action}",
        ]
        if request.description:
            message_lines.append(f"描述：{request.description}")
        message_lines.extend(
            [
                "指令：",
                f"  • /approve {request.id}  # 批准本次请求",
                f"  • /approve-session {request.id}  # 本会话自动批准",
                f"  • /reject {request.id}  # 拒绝",
            ]
        )
        console.print(
            Panel.fit(
                Text("\n".join(message_lines)),
                title="审批请求",
                border_style="yellow",
            )
        )
        if self._on_waiting_approval:
            self._on_waiting_approval(entry)
        self._notify_change()

    def resolve_approval(self, approval_id: str, response: ApprovalResponse) -> str:
        entry = self._approvals.pop(approval_id, None)
        if entry is None:
            return "未找到匹配的审批请求。"
        task = self.get(entry.task_id)
        if task:
            task.pending_approvals.discard(approval_id)
            if not task.pending_approvals and task.status == TaskStatus.WAITING_APPROVAL:
                task.status = TaskStatus.RUNNING
                task.last_active_at = datetime.now()
        entry.request.resolve(response)
        action = {
            ApprovalResponse.APPROVE: "已批准",
            ApprovalResponse.APPROVE_FOR_SESSION: "已在本会话内自动批准",
            ApprovalResponse.REJECT: "已拒绝",
        }[response]
        self._log(entry.task_id, f"{action}审批请求 {approval_id}", style="cyan")
        if self._on_approval_resolved:
            self._on_approval_resolved(entry, response)
        self._notify_change()
        return f"{action}。"

    def mark_succeeded(self, task_id: int) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.SUCCEEDED
            task.finished_at = datetime.now()
            task.last_active_at = task.finished_at
            task.fade_deadline = task.finished_at + timedelta(seconds=3)
            self._log(task_id, "完成", style="green")
            self._notify_change()

    def mark_failed(self, task_id: int, reason: str) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.FAILED
            task.finished_at = datetime.now()
            task.last_active_at = task.finished_at
            task.fade_deadline = task.finished_at + timedelta(seconds=3)
            self._log(task_id, f"失败：{reason}", style="red")
            self._notify_change()

    def mark_cancelling(self, task_id: int) -> None:
        if task := self.get(task_id):
            if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                return
            task.status = TaskStatus.CANCELLING
            task.last_active_at = datetime.now()
            self._log(task_id, "正在尝试取消", style="yellow")
            self._notify_change()

    def mark_cancelled(self, task_id: int, reason: str | None = None) -> None:
        if task := self.get(task_id):
            task.status = TaskStatus.CANCELLED
            task.finished_at = datetime.now()
            task.last_active_at = task.finished_at
            task.fade_deadline = task.finished_at + timedelta(seconds=3)
            msg = "已取消" + (f"：{reason}" if reason else "")
            self._log(task_id, msg, style="yellow")
            self._notify_change()

    def drop_pending_approvals(self, task_id: int, response: ApprovalResponse) -> None:
        task = self.get(task_id)
        if task is None:
            return
        for approval_id in list(task.pending_approvals):
            self.resolve_approval(approval_id, response)
        self._notify_change()

    def approvals(self) -> list[ApprovalEntry]:
        return list(self._approvals.values())

    def append_log(
        self,
        task_id: int,
        message: str,
        *,
        style: str | None = None,
        plain: bool = False,
        silent: bool = False,
    ) -> None:
        if task := self.get(task_id):
            task.logs.append(message)
            if len(task.logs) > 20:
                task.logs.pop(0)
            task.last_active_at = datetime.now()
        self._log(task_id, message, style=style, plain=plain, silent=silent)
        self._notify_change()

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

    def _touch(self, task: ShellTask | None) -> None:
        if task is None:
            return
        task.last_active_at = datetime.now()

    def _notify_change(self) -> None:
        if self._on_tasks_changed:
            self._on_tasks_changed()

    def _log(
        self,
        task_id: int,
        message: str,
        *,
        style: str | None = None,
        plain: bool = False,
        silent: bool = False,
    ) -> None:
        if silent:
            return
        applied_style = style if style or plain else "grey70"
        body = Text(message, style=applied_style or "")
        console.print(body)


class ShellTaskManager:
    """Manage background execution of soul commands in Shell UI."""

    def __init__(
        self,
        soul: Soul,
        *,
        banner_settings: TaskBannerSettings | None = None,
        on_waiting_approval: ApprovalWaitCallback | None = None,
        on_approval_resolved: ApprovalResolvedCallback | None = None,
    ):
        self._soul = soul
        self._banner_settings = banner_settings or TaskBannerSettings()
        self._store = TaskStateStore(
            on_waiting_approval=on_waiting_approval,
            on_approval_resolved=on_approval_resolved,
            on_tasks_changed=self._handle_tasks_changed,
        )
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._executor_task: asyncio.Task[None] | None = None
        self._banner = TaskBanner(
            self._store,
            self._banner_settings,
        )
        self._live_updater: Callable[[], None] | None = None
        self._live_overlays: list[Callable[[], RenderableType | None]] = []
        self._banner.set_invalidator(self._handle_banner_refresh)

    def start(self) -> None:
        if self._executor_task is None:
            self._executor_task = asyncio.create_task(self._executor_loop())
        self._banner.start()

    async def shutdown(self) -> None:
        if self._executor_task:
            self._executor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._executor_task
            self._executor_task = None
        await self._banner.stop()

    def set_live_updater(self, callback: Callable[[], None] | None) -> None:
        self._live_updater = callback

    def push_live_overlay(
        self, provider: Callable[[], RenderableType | None]
    ) -> Callable[[], None]:
        self._live_overlays.append(provider)
        self._banner.request_refresh(force=True)

        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._live_overlays.remove(provider)
            self._banner.request_refresh(force=True)

        return _remove

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

    def _handle_tasks_changed(self) -> None:
        self._banner.request_refresh()

    def render_live(self) -> RenderableType:
        renderables: list[RenderableType] = []
        banner = self._banner.render()
        if banner is not None:
            renderables.append(banner)
        for provider in list(self._live_overlays):
            extra = provider()
            if extra is not None:
                renderables.append(extra)
        if not renderables:
            return Text("")
        if len(renderables) == 1:
            return renderables[0]
        return Group(*renderables)

    def _handle_banner_refresh(self) -> None:
        if self._live_updater:
            self._live_updater()

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
                task.user_input if isinstance(task.user_input, str) else list(task.user_input),
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

    MAX_BASH_TRANSCRIPT_LINES = 6

    def __init__(self, store: TaskStateStore, task_id: int):
        self._store = store
        self._task_id = task_id
        self._tool_names: dict[str, str] = {}
        self._text_buffer: list[str] = []

    async def observe(self, wire: WireUISide) -> None:
        while True:
            try:
                msg = await wire.receive()
            except asyncio.QueueShutDown:
                self._flush_pending_text()
                return
            self._handle_message(msg)

    def _handle_message(self, msg: WireMessage) -> None:
        if isinstance(msg, TextPart):
            snippet = self._content_snippet(msg)
            if snippet:
                self._text_buffer.append(snippet)
            return

        self._flush_pending_text()

        match msg:
            case StepBegin():
                self._store.append_log(self._task_id, f"Step {msg.n} 开始", silent=True)
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
            case ThinkPart() as part:
                snippet = self._content_snippet(part)
                if snippet:
                    self._store.append_log(self._task_id, snippet, style="grey50")
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
                if name == "Bash" and isinstance(result.result.output, str):
                    self._log_bash_transcript(result.result.output)
            case ApprovalRequest():
                self._store.mark_waiting_approval(self._task_id, msg)
            case SubagentEvent():
                # 子代理事件通常是噪声，忽略即可。
                return
            case _:
                self._store.append_log(self._task_id, f"收到事件 {type(msg).__name__}")

    @staticmethod
    def _content_snippet(part: ContentPart) -> str | None:
        if isinstance(part, TextPart):
            text = part.text
            if not text or not text.strip():
                return None
            return text
        if isinstance(part, ThinkPart):
            text = part.think.strip()
            if not text:
                return None
            prefix = "思考"
            body = text if len(text) <= 100 else text[:97] + "…"
            return f"[{prefix}] {body}"
        return None

    def _flush_pending_text(self) -> None:
        if not self._text_buffer:
            return
        text = "".join(self._text_buffer)
        self._text_buffer.clear()
        self._store.append_log(self._task_id, text, plain=True)

    def _log_bash_transcript(self, transcript: str) -> None:
        transcript = transcript.strip()
        if not transcript:
            return
        lines = transcript.splitlines()
        max_lines = self.MAX_BASH_TRANSCRIPT_LINES
        shown = lines[:max_lines]
        remainder = len(lines) - len(shown)
        for line in shown:
            self._store.append_log(self._task_id, line, plain=True)
        if remainder > 0:
            self._store.append_log(
                self._task_id,
                f"… +{remainder} lines",
                style="grey50",
                plain=True,
            )


class TaskBanner:
    """Produce a rich renderable banner for active tasks."""

    GRADIENTS: list[tuple[str, str]] = [
        ("53b3ff", "c56bff"),
        ("5fd6ff", "a86bff"),
        ("64c9ff", "f38bff"),
        ("6bd9ff", "de93ff"),
    ]
    LIMITED_STYLES = ["ansicyan", "ansimagenta", "ansiblue", "ansiviolet"]
    ASCII_SPINNER = ["-", "\\", "|", "/"]
    BRAILLE_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    FINAL_STATUSES = {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
    MUTED_STYLE = "fg:#6d6f7a"

    def __init__(
        self,
        store: TaskStateStore,
        settings: TaskBannerSettings,
        *,
        on_refresh: Callable[[], None] | None = None,
    ):
        self._store = store
        self._settings = settings
        self._on_refresh = on_refresh
        self._frame = 0
        self._task: asyncio.Task[None] | None = None
        self._color_mode = self._detect_color_mode()
        self._refresh_event = asyncio.Event()
        self._force_next_refresh = False
        self._last_render_at = time.monotonic() - self._settings.refresh_interval
        self._idle_rendered = False

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        self._refresh_event.set()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def set_invalidator(self, callback: Callable[[], None]) -> None:
        self._on_refresh = callback

    def request_refresh(self, *, force: bool = False) -> None:
        if force:
            self._force_next_refresh = True
        self._idle_rendered = False
        self._refresh_event.set()

    async def _loop(self) -> None:
        interval = self._settings.refresh_interval
        while True:
            timeout = interval if self._has_active_lines() else None
            try:
                if timeout is None:
                    await self._refresh_event.wait()
                else:
                    await asyncio.wait_for(self._refresh_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
            self._refresh_event.clear()
            now = time.monotonic()
            if not self._force_next_refresh:
                elapsed = now - self._last_render_at
                if timeout is not None and elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                    now = time.monotonic()
            self._last_render_at = now
            idle = not self._has_active_lines()
            if idle and not self._force_next_refresh and self._idle_rendered:
                continue
            self._idle_rendered = idle
            self._force_next_refresh = False
            self._frame = (self._frame + 1) % 10_000
            if self._on_refresh:
                self._on_refresh()

    def render(self) -> RenderableType | None:
        visible, hidden, now = self._visible_tasks_for_render()
        lines: list[Text] = []
        if not visible and hidden == 0:
            line = Text("暂无任务，执行命令后会显示进度。\n", style=self.MUTED_STYLE)
            lines.append(line)
        else:
            for task in visible:
                lines.append(self._render_task_line(task, now))
            if hidden:
                summary = Text(f"+{hidden} more (use /tasks)\n", style=self.MUTED_STYLE)
                lines.append(summary)
        if not lines:
            return None
        return Group(*lines)

    def _visible_tasks_for_render(
        self, now: datetime | None = None
    ) -> tuple[list[ShellTask], int, datetime]:
        now = now or datetime.now()
        active: list[ShellTask] = []
        trailing: list[ShellTask] = []
        for task in self._store.tasks():
            if task.status in self.FINAL_STATUSES:
                if task.fade_deadline and now >= task.fade_deadline:
                    continue
                trailing.append(task)
            else:
                active.append(task)
        active.sort(key=lambda t: t.last_active_at or t.created_at, reverse=True)
        trailing.sort(
            key=lambda t: (t.finished_at or t.last_active_at or t.created_at),
            reverse=True,
        )
        ordered = active + trailing
        slots = max(1, self._settings.visible_slots)
        visible = ordered[:slots]
        hidden = max(len(ordered) - slots, 0)
        return visible, hidden, now

    def _render_task_line(self, task: ShellTask, now: datetime) -> Text:
        parts: list[tuple[str, str]] = []
        badge_style = self._badge_style(task)
        parts.append((badge_style, "■ "))
        header = f"#{task.id} • {task.short_command(40)} "
        header_style = "fg:#d7dcff bold" if self._color_mode != ColorMode.MONO else "bold"
        parts.append((header_style, header))
        status_fragments = self._status_fragments(task, now)
        parts.extend(status_fragments)
        text = Text()
        for style, chunk in parts:
            text.append(chunk, style=style)
        if not text.plain.endswith("\n"):
            text.append("\n")
        return text

    def _badge_style(self, task: ShellTask) -> str:
        if self._color_mode == ColorMode.MONO:
            return "fg:#777777"
        if self._color_mode == ColorMode.LIMITED:
            return self.LIMITED_STYLES[task.id % len(self.LIMITED_STYLES)]
        start, _ = self._gradient_for_task(task)
        return f"fg:#{start}"

    def _status_fragments(self, task: ShellTask, now: datetime) -> list[tuple[str, str]]:
        spinner = self._spinner_for(task)
        label, hint = self._status_label_and_hint(task)
        elapsed = self._format_elapsed(task, now)
        details: list[str] = []
        if elapsed:
            details.append(elapsed)
        if hint:
            details.append(hint)
        text = f"{spinner} {label}"
        if details:
            text += f" ({' • '.join(details)})"
        if self._color_mode == ColorMode.TRUECOLOR:
            start, end = self._gradient_for_task(task)
            return self._apply_gradient(text, start, end)
        if self._color_mode == ColorMode.LIMITED:
            style = self.LIMITED_STYLES[task.id % len(self.LIMITED_STYLES)]
            return [(style, text)]
        return [("bold", text)]

    def _apply_gradient(self, text: str, start: str, end: str) -> list[tuple[str, str]]:
        if not text:
            return []
        start_rgb = tuple(int(start[i : i + 2], 16) for i in (0, 2, 4))
        end_rgb = tuple(int(end[i : i + 2], 16) for i in (0, 2, 4))
        length = max(1, len(text))
        fragments: list[tuple[str, str]] = []
        for index, char in enumerate(text):
            ratio = index / max(1, length - 1)
            r = round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
            g = round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
            b = round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
            fragments.append((f"fg:#{r:02x}{g:02x}{b:02x}", char))
        return fragments

    def _gradient_for_task(self, task: ShellTask) -> tuple[str, str]:
        return self.GRADIENTS[task.id % len(self.GRADIENTS)]

    def _spinner_for(self, task: ShellTask) -> str:
        if task.status in {TaskStatus.RUNNING, TaskStatus.CANCELLING}:
            frames = self.BRAILLE_SPINNER if self._color_mode != ColorMode.MONO else self.ASCII_SPINNER
            idx = (self._frame + task.id) % len(frames)
            return frames[idx]
        if task.status == TaskStatus.WAITING_APPROVAL:
            return "⧗" if self._color_mode != ColorMode.MONO else "?"
        if task.status == TaskStatus.QUEUED:
            return "…" if self._color_mode != ColorMode.MONO else "."
        if task.status == TaskStatus.SUCCEEDED:
            return "✓"
        if task.status == TaskStatus.FAILED:
            return "✕" if self._color_mode != ColorMode.MONO else "x"
        if task.status == TaskStatus.CANCELLED:
            return "⊘" if self._color_mode != ColorMode.MONO else "!"
        return "-"

    def _status_label_and_hint(self, task: ShellTask) -> tuple[str, str | None]:
        match task.status:
            case TaskStatus.RUNNING:
                return "Working", "esc to interrupt"
            case TaskStatus.CANCELLING:
                return "Cancelling", None
            case TaskStatus.WAITING_APPROVAL:
                return "Waiting approval", "/approvals"
            case TaskStatus.QUEUED:
                return "Queued", f"/cancel {task.id}"
            case TaskStatus.SUCCEEDED:
                return "Done", None
            case TaskStatus.FAILED:
                return "Failed", "check logs"
            case TaskStatus.CANCELLED:
                return "Cancelled", None
            case _:
                return task.status.value, None

    def _format_elapsed(self, task: ShellTask, now: datetime) -> str:
        base = task.started_at or task.created_at
        end = task.finished_at or now
        delta = max(0, int((end - base).total_seconds()))
        if delta < 60:
            return f"{delta}s"
        minutes, seconds = divmod(delta, 60)
        if minutes < 60:
            return f"{minutes}m {seconds:02d}s"
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours}h {minutes}m"
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h"

    def _detect_color_mode(self) -> ColorMode:
        if console.no_color or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
            return ColorMode.MONO
        system = console.color_system or ""
        if system == "truecolor":
            return ColorMode.TRUECOLOR
        if system in {"standard", "eight_bit", "windows"}:
            return ColorMode.LIMITED
        return ColorMode.MONO

    def _has_active_lines(self) -> bool:
        now = datetime.now()
        for task in self._store.tasks():
            if task.status not in self.FINAL_STATUSES:
                return True
            if task.fade_deadline and now < task.fade_deadline:
                return True
        return False
