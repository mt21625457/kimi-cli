from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import Any

from kosong.chat_provider import APIStatusError, ChatProviderError
from kosong.message import ContentPart
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kimi_cli.config import Config
from kimi_cli.soul import LLMNotSet, LLMNotSupported, MaxStepsReached, RunCancelled, Soul, run_soul
from kimi_cli.soul.kimisoul import KimiSoul
from kimi_cli.ui.shell.console import console
from kimi_cli.ui.shell.metacmd import get_meta_command
from kimi_cli.ui.shell.prompt import CustomPromptSession, PromptMode, UserInput, toast
from kimi_cli.ui.shell.replay import replay_recent_history
from kimi_cli.ui.shell.task_manager import (
    ApprovalEntry,
    ShellTaskManager,
    TaskBannerSettings,
)
from kimi_cli.ui.shell.update import LATEST_VERSION_FILE, UpdateResult, do_update, semver_tuple
from kimi_cli.ui.shell.visualize import visualize
from kimi_cli.utils.logging import logger
from kimi_cli.utils.signals import install_sigint_handler
from kimi_cli.utils.term import ensure_new_line
from kimi_cli.wire.message import ApprovalResponse


class ShellApp:
    def __init__(
        self,
        soul: Soul,
        welcome_info: list[WelcomeInfoItem] | None = None,
        config: Config | None = None,
    ):
        self.soul = soul
        self._welcome_info = list(welcome_info or [])
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._task_manager: ShellTaskManager | None = None
        self._pending_approval_ids: set[str] = set()
        self._config = config

    async def run(self, command: str | None = None) -> bool:
        if command is not None:
            # run single command and exit
            logger.info("Running agent with command: {command}", command=command)
            return await self._run_soul_command(command)

        self._start_background_task(self._auto_update())

        _print_welcome_info(self.soul.name or "Kimi CLI", self._welcome_info)

        if isinstance(self.soul, KimiSoul):
            await replay_recent_history(self.soul.context.history)

        banner_settings = TaskBannerSettings.from_config(self._config)
        manager = ShellTaskManager(
            self.soul,
            banner_settings=banner_settings,
            on_waiting_approval=self._on_waiting_approval,
            on_approval_resolved=self._on_approval_resolved,
        )
        manager.start()
        self._task_manager = manager
        try:
            with patch_stdout(raw=True):
                refresh_hz = max(0.1, 1.0 / max(0.1, banner_settings.refresh_interval))
                with Live(
                    manager.render_live(),
                    console=console,
                    refresh_per_second=refresh_hz,
                    transient=False,
                    vertical_overflow="visible",
                ) as live:
                    manager.set_live_updater(lambda: live.update(manager.render_live()))
                    try:
                        with CustomPromptSession(
                            status_provider=lambda: self.soul.status,
                            status_note_provider=self._approval_status_note,
                            model_capabilities=self.soul.model_capabilities or set(),
                            initial_thinking=isinstance(self.soul, KimiSoul) and self.soul.thinking,
                        ) as prompt_session:
                            while True:
                                try:
                                    ensure_new_line()
                                    user_input = await prompt_session.prompt()
                                except KeyboardInterrupt:
                                    logger.debug("Exiting by KeyboardInterrupt")
                                    console.print(
                                        "[grey50]Tip: press Ctrl-D or send 'exit' to quit[/grey50]"
                                    )
                                    continue
                                except EOFError:
                                    logger.debug("Exiting by EOF")
                                    console.print("Bye!")
                                    break

                                if not user_input:
                                    logger.debug("Got empty input, skipping")
                                    continue
                                logger.debug("Got user input: {user_input}", user_input=user_input)

                                if user_input.command in ["exit", "quit", "/exit", "/quit"]:
                                    logger.debug("Exiting by meta command")
                                    console.print("Bye!")
                                    break

                                if user_input.mode == PromptMode.SHELL:
                                    await self._run_shell_command(user_input.command)
                                    continue

                                if user_input.command.startswith("/"):
                                    logger.debug(
                                        "Running meta command: {command}", command=user_input.command
                                    )
                                    await self._run_meta_command(user_input.command[1:])
                                    continue

                                logger.info(
                                    "Queue agent command: {command} with thinking {thinking}",
                                    command=user_input.content,
                                    thinking="on" if user_input.thinking else "off",
                                )
                                self._enqueue_agent_command(user_input)
                    finally:
                        manager.set_live_updater(None)
        finally:
            await manager.shutdown()
            self._task_manager = None

        return True

    async def _run_shell_command(self, command: str) -> None:
        """Run a shell command in foreground."""
        if not command.strip():
            return

        logger.info("Running shell command: {cmd}", cmd=command)

        proc: asyncio.subprocess.Process | None = None

        def _handler():
            logger.debug("SIGINT received.")
            if proc:
                proc.terminate()

        loop = asyncio.get_running_loop()
        remove_sigint = install_sigint_handler(loop, _handler)
        try:
            # TODO: For the sake of simplicity, we now use `create_subprocess_shell`.
            # Later we should consider making this behave like a real shell.
            proc = await asyncio.create_subprocess_shell(command)
            await proc.wait()
        except Exception as e:
            logger.exception("Failed to run shell command:")
            console.print(f"[red]Failed to run shell command: {e}[/red]")
        finally:
            remove_sigint()

    async def _run_meta_command(self, command_str: str):
        from kimi_cli.cli import Reload

        parts = command_str.split(" ")
        command_name = parts[0]
        command_args = parts[1:]
        command = get_meta_command(command_name)
        if command is None:
            console.print(f"Meta command /{command_name} not found")
            return
        if command.kimi_soul_only and not isinstance(self.soul, KimiSoul):
            console.print(f"Meta command /{command_name} not supported")
            return
        logger.debug(
            "Running meta command: {command_name} with args: {command_args}",
            command_name=command_name,
            command_args=command_args,
        )
        try:
            ret = command.func(self, command_args)
            if isinstance(ret, Awaitable):
                await ret
        except LLMNotSet:
            logger.error("LLM not set")
            console.print("[red]LLM not set, send /setup to configure[/red]")
        except ChatProviderError as e:
            logger.exception("LLM provider error:")
            console.print(f"[red]LLM provider error: {e}[/red]")
        except asyncio.CancelledError:
            logger.info("Interrupted by user")
            console.print("[red]Interrupted by user[/red]")
        except Reload:
            # just propagate
            raise
        except BaseException as e:
            logger.exception("Unknown error:")
            console.print(f"[red]Unknown error: {e}[/red]")
            raise  # re-raise unknown error

    def _enqueue_agent_command(self, user_input: UserInput) -> None:
        payload: str | list[ContentPart]
        payload = user_input.content if user_input.content else user_input.command
        if self._task_manager is None:
            # fallback (should not happen in interactive mode)
            self._start_background_task(self._run_soul_command(payload, user_input.thinking))
            return
        self._task_manager.submit(
            command_text=user_input.command,
            user_input=payload,
            thinking=user_input.thinking,
        )

    def _on_waiting_approval(self, entry: ApprovalEntry) -> None:
        self._pending_approval_ids.add(entry.request.id)
        toast(
            (
                f"审批等待：{entry.request.sender} 想要 {entry.request.action}. "
                f"运行 /approve {entry.request.id} 进行授权"
            ),
            topic="approval",
            duration=6.0,
            immediate=True,
        )

    def _on_approval_resolved(self, entry: ApprovalEntry, response: ApprovalResponse) -> None:
        self._pending_approval_ids.discard(entry.request.id)
        if response is ApprovalResponse.REJECT:
            toast(
                f"已拒绝审批 {entry.request.id}",
                topic="approval",
                duration=4.0,
                immediate=True,
            )
        else:
            toast(
                f"已处理审批 {entry.request.id}",
                topic="approval",
                duration=4.0,
                immediate=True,
            )

    def _approval_status_note(self) -> str | None:
        if not self._pending_approval_ids:
            return None
        count = len(self._pending_approval_ids)
        return f"审批待处理: {count}"

    def _require_task_manager(self) -> ShellTaskManager | None:
        if self._task_manager is None:
            console.print("[grey50]任务队列仅在交互式 Shell 模式可用。[/grey50]")
            return None
        return self._task_manager

    def show_tasks(self) -> None:
        manager = self._require_task_manager()
        if manager is None:
            return
        console.print(manager.list_tasks())

    def show_approvals(self) -> None:
        manager = self._require_task_manager()
        if manager is None:
            return
        approvals = manager.list_approvals()
        if not approvals:
            console.print("[grey50]暂无待处理审批。[/grey50]")
            return
        table = Table(title="待审批操作", box=None, show_lines=False)
        table.add_column("审批ID", style="cyan")
        table.add_column("任务", justify="right")
        table.add_column("请求方", style="blue")
        table.add_column("描述")
        for entry in approvals:
            table.add_row(
                entry.request.id,
                str(entry.task_id),
                entry.request.sender,
                entry.request.description,
            )
        console.print(table)

    def respond_approval(self, approval_id: str, response: ApprovalResponse) -> None:
        manager = self._require_task_manager()
        if manager is None:
            return
        console.print(manager.resolve_approval(approval_id, response))

    def cancel_task(self, task_id_text: str) -> None:
        manager = self._require_task_manager()
        if manager is None:
            return
        try:
            task_id = int(task_id_text)
        except ValueError:
            console.print("[red]任务 ID 必须是数字。[/red]")
            return
        console.print(manager.cancel_task(task_id))

    async def _run_soul_command(
        self,
        user_input: str | list[ContentPart],
        thinking: bool | None = None,
    ) -> bool:
        """
        Run the soul and handle any known exceptions.

        Returns:
            bool: Whether the run is successful.
        """
        cancel_event = asyncio.Event()

        def _handler():
            logger.debug("SIGINT received.")
            cancel_event.set()

        loop = asyncio.get_running_loop()
        remove_sigint = install_sigint_handler(loop, _handler)

        try:
            if isinstance(self.soul, KimiSoul) and thinking is not None:
                self.soul.set_thinking(thinking)

            # Use lambda to pass cancel_event via closure
            await run_soul(
                self.soul,
                user_input,
                lambda wire: visualize(
                    wire,
                    initial_status=self.soul.status,
                    cancel_event=cancel_event,
                ),
                cancel_event,
            )
            return True
        except LLMNotSet:
            logger.error("LLM not set")
            console.print("[red]LLM not set, send /setup to configure[/red]")
        except LLMNotSupported as e:
            # actually unsupported input/mode should already be blocked by prompt session
            logger.error(
                "LLM model '{model_name}' does not support required capabilities: {capabilities}",
                model_name=e.llm.model_name,
                capabilities=", ".join(e.capabilities),
            )
            console.print(f"[red]{e}[/red]")
        except ChatProviderError as e:
            logger.exception("LLM provider error:")
            if isinstance(e, APIStatusError) and e.status_code == 401:
                console.print("[red]Authorization failed, please check your API key[/red]")
            elif isinstance(e, APIStatusError) and e.status_code == 402:
                console.print("[red]Membership expired, please renew your plan[/red]")
            elif isinstance(e, APIStatusError) and e.status_code == 403:
                console.print("[red]Quota exceeded, please upgrade your plan or retry later[/red]")
            else:
                console.print(f"[red]LLM provider error: {e}[/red]")
        except MaxStepsReached as e:
            logger.warning("Max steps reached: {n_steps}", n_steps=e.n_steps)
            console.print(f"[yellow]Max steps reached: {e.n_steps}[/yellow]")
        except RunCancelled:
            logger.info("Cancelled by user")
            console.print("[red]Interrupted by user[/red]")
        except BaseException as e:
            logger.exception("Unknown error:")
            console.print(f"[red]Unknown error: {e}[/red]")
            raise  # re-raise unknown error
        finally:
            remove_sigint()
        return False

    async def _auto_update(self) -> None:
        toast("checking for updates...", topic="update", duration=2.0)
        result = await do_update(print=False, check_only=True)
        if result == UpdateResult.UPDATE_AVAILABLE:
            console.print(
                "[yellow]New version available. Run `[bold]uv tool upgrade kimi-cli[/bold]` to upgrade.[/yellow]"
            )
        elif result == UpdateResult.UPDATED:
            toast("auto updated, restart to use the new version", topic="update", duration=5.0)

    def _start_background_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _cleanup(t: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(t)
            try:
                t.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Background task failed:")

        task.add_done_callback(_cleanup)
        return task


_KIMI_BLUE = "dodger_blue1"
_LOGO = f"""\
[{_KIMI_BLUE}]\
▐█▛█▛█▌
▐█████▌\
[{_KIMI_BLUE}]\
"""


@dataclass(slots=True)
class WelcomeInfoItem:
    class Level(Enum):
        INFO = "grey50"
        WARN = "yellow"
        ERROR = "red"

    name: str
    value: str
    level: Level = Level.INFO


def _print_welcome_info(name: str, info_items: list[WelcomeInfoItem]) -> None:
    head = Text.from_markup(f"[bold]Welcome to {name}![/bold]")
    help_text = Text.from_markup("[grey50]Send /help for help information.[/grey50]")

    # Use Table for precise width control
    logo = Text.from_markup(_LOGO)
    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1), expand=False)
    table.add_column(justify="left")
    table.add_column(justify="left")
    table.add_row(logo, Group(head, help_text))

    rows: list[RenderableType] = [table]

    rows.append(Text(""))  # Empty line
    for item in info_items:
        rows.append(Text(f"{item.name}: {item.value}", style=item.level.value))

    if LATEST_VERSION_FILE.exists():
        from kimi_cli.constant import VERSION as current_version

        latest_version = LATEST_VERSION_FILE.read_text(encoding="utf-8").strip()
        if semver_tuple(latest_version) > semver_tuple(current_version):
            rows.append(
                Text.from_markup(
                    f"\n[yellow]New version available: {latest_version}. "
                    "Please run `uv tool upgrade kimi-cli` to upgrade.[/yellow]"
                )
            )

    console.print(
        Panel(
            Group(*rows),
            border_style=_KIMI_BLUE,
            expand=False,
            padding=(1, 2),
        )
    )
