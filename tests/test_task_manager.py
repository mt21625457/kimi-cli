from __future__ import annotations

from unittest.mock import patch

from kosong.tooling import ToolOk, ToolResult

from kimi_cli.ui.shell.task_manager import TaskStateStore, _TaskObserver


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
