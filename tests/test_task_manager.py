from __future__ import annotations

from unittest.mock import MagicMock, patch

from kosong.tooling import ToolOk, ToolResult
from rich.console import Group
from rich.text import Text

from kimi_cli.ui.shell.task_manager import (
    ShellTaskManager,
    TaskBannerSettings,
    TaskStateStore,
    _TaskObserver,
)


@patch("kimi_cli.ui.shell.task_manager.console.print")
def test_bash_transcript_truncated(mock_print):  # noqa: ARG001
    store = TaskStateStore()
    task = store.create_task(command_text="echo hi", user_input="hi", thinking=None)

    observer = _TaskObserver(store, task.id)
    observer._tool_names["tool-1"] = "Bash"

    transcript_lines = [f"line {i}" for i in range(1, 11)]
    transcript = "\n" + "\n".join(transcript_lines) + "\n"
    observer._handle_message(
        ToolResult(
            tool_call_id="tool-1",
            result=ToolOk(output=transcript, message="", brief=""),
        )
    )

    logs = store.get(task.id).logs
    assert "line 1" in logs
    assert "line 6" in logs
    assert "line 7" not in logs
    assert any(entry.startswith("… +") for entry in logs)


def test_shell_task_manager_live_overlay_stack():
    manager = ShellTaskManager(MagicMock(), banner_settings=TaskBannerSettings())
    overlay_calls = 0

    def overlay():
        nonlocal overlay_calls
        overlay_calls += 1
        return Text("watch table\n")

    remove_overlay = manager.push_live_overlay(overlay)
    renderable = manager.render_live()
    assert isinstance(renderable, Group)
    assert overlay_calls == 1

    remove_overlay()
    manager.render_live()
    assert overlay_calls == 1
