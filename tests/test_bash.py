"""Tests for the shell tool."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest
from kosong.tooling import ToolError, ToolOk

from kimi_cli.config import Config
from kimi_cli.tools.bash import Bash, Params
from tests.conftest import tool_call_context

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows", reason="Bash tool tests are disabled on Windows."
)


def _transcript_lines(output: str) -> list[str]:
    return output.rstrip("\n").splitlines()


def _assert_header(lines: list[str], command: str, *, scan: bool = False) -> None:
    expected = f"• Ran {command}"
    if scan:
        expected += " (scan)"
    assert lines[0] == expected


def _body_contains(lines: list[str], text: str) -> bool:
    return any(text in line for line in lines[1:-1])


@pytest.mark.asyncio
async def test_simple_command(bash_tool: Bash):
    result = await bash_tool(Params(command="echo 'Hello World'"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo 'Hello World'")
    assert "  │ Hello World" in lines
    assert lines[-1] == "  └ (exit 0)"
    assert result.message == "Command executed successfully."


@pytest.mark.asyncio
async def test_command_with_error(bash_tool: Bash):
    result = await bash_tool(Params(command="ls /nonexistent/directory"))
    assert isinstance(result, ToolError)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "ls /nonexistent/directory")
    assert any("No such file or directory" in line for line in lines)
    assert "exit" in lines[-1] and "failed" in lines[-1]
    assert "Command failed with exit code:" in result.message


@pytest.mark.asyncio
async def test_command_chaining(bash_tool: Bash):
    result = await bash_tool(Params(command="echo 'First' && echo 'Second'"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo 'First' && echo 'Second'")
    assert _body_contains(lines, "First")
    assert _body_contains(lines, "Second")
    assert lines[-1] == "  └ (exit 0)"


@pytest.mark.asyncio
async def test_command_sequential(bash_tool: Bash):
    result = await bash_tool(Params(command="echo 'One'; echo 'Two'"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo 'One'; echo 'Two'")
    assert _body_contains(lines, "One")
    assert _body_contains(lines, "Two")
    assert lines[-1] == "  └ (exit 0)"


@pytest.mark.asyncio
async def test_command_conditional(bash_tool: Bash):
    result = await bash_tool(Params(command="false || echo 'Success'"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "false || echo 'Success'")
    assert _body_contains(lines, "Success")
    assert lines[-1] == "  └ (exit 0)"


@pytest.mark.asyncio
async def test_command_pipe(bash_tool: Bash):
    result = await bash_tool(Params(command="echo 'Hello World' | wc -w"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo 'Hello World' | wc -w")
    assert "2" in "".join(lines[1:-1])
    assert lines[-1] == "  └ (exit 0)"


@pytest.mark.asyncio
async def test_multiple_pipes(bash_tool: Bash):
    result = await bash_tool(Params(command="echo -e '1\\n2\\n3' | grep '2' | wc -l"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo -e '1\\n2\\n3' | grep '2' | wc -l")
    assert "1" in "".join(lines[1:-1])
    assert lines[-1] == "  └ (exit 0)"


@pytest.mark.asyncio
async def test_command_with_timeout(bash_tool: Bash):
    result = await bash_tool(Params(command="sleep 0.1", timeout=1))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "sleep 0.1")
    assert lines[-1] == "  └ (exit 0, no output)"


@pytest.mark.asyncio
async def test_command_timeout_expires(bash_tool: Bash):
    result = await bash_tool(Params(command="sleep 2", timeout=1))
    assert isinstance(result, ToolError)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "sleep 2")
    assert lines[-1] == "  └ (timeout (1s), no output)"
    assert "Command killed by timeout" in result.message


@pytest.mark.asyncio
async def test_environment_variables(bash_tool: Bash):
    result = await bash_tool(Params(command="export TEST_VAR='test_value' && echo $TEST_VAR"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "export TEST_VAR='test_value' && echo $TEST_VAR")
    assert _body_contains(lines, "test_value")


@pytest.mark.asyncio
async def test_file_operations(bash_tool: Bash, temp_work_dir: Path):
    result = await bash_tool(Params(command=f"echo 'Test content' > {temp_work_dir}/test_file.txt"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, f"echo 'Test content' > {temp_work_dir}/test_file.txt")
    assert lines[-1] == "  └ (exit 0, no output)"

    result = await bash_tool(Params(command=f"cat {temp_work_dir}/test_file.txt"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, f"cat {temp_work_dir}/test_file.txt")
    assert _body_contains(lines, "Test content")


@pytest.mark.asyncio
async def test_text_processing(bash_tool: Bash):
    result = await bash_tool(
        Params(command="echo 'apple banana cherry' | sed 's/banana/orange/'")
    )
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo 'apple banana cherry' | sed 's/banana/orange/'")
    assert _body_contains(lines, "apple orange cherry")


@pytest.mark.asyncio
async def test_command_substitution(bash_tool: Bash):
    result = await bash_tool(Params(command='echo "Result: $(echo hello)"'))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, 'echo "Result: $(echo hello)"')
    assert _body_contains(lines, "Result: hello")


@pytest.mark.asyncio
async def test_arithmetic_substitution(bash_tool: Bash):
    result = await bash_tool(Params(command='echo "Answer: $((2 + 2))"'))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, 'echo "Answer: $((2 + 2))"')
    assert _body_contains(lines, "Answer: 4")


@pytest.mark.asyncio
async def test_very_long_output(bash_tool: Bash):
    result = await bash_tool(Params(command="seq 1 100 | head -50"))
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "seq 1 100 | head -50")
    assert any(line.endswith("1") for line in lines[1:5])
    assert "  │ … +30 lines" in lines
    assert "output truncated" in lines[-1]


@pytest.mark.asyncio
async def test_output_truncation_on_success(bash_tool: Bash):
    result = await bash_tool(
        Params(command="python3 -c \"print('X' * 6000)\"")
    )
    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "python3 -c \"print('X' * 6000)\"")
    assert "[...truncated]" in "".join(lines)
    assert "output truncated" in lines[-1]


@pytest.mark.asyncio
async def test_output_truncation_on_failure(bash_tool: Bash):
    result = await bash_tool(
        Params(command="python3 -c \"import sys; print('ERR'*8000); sys.exit(1)\"")
    )
    assert isinstance(result, ToolError)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "python3 -c \"import sys; print('ERR'*8000); sys.exit(1)\"")
    assert "[...truncated]" in "".join(lines)
    assert "output truncated" in lines[-1]
    assert "failed" in lines[-1]


@pytest.mark.asyncio
async def test_timeout_parameter_validation_bounds():
    with pytest.raises(ValueError, match="timeout"):
        Params(command="echo test", timeout=0)

    with pytest.raises(ValueError, match="timeout"):
        Params(command="echo test", timeout=-1)

    from kimi_cli.tools.bash import MAX_TIMEOUT

    with pytest.raises(ValueError, match="timeout"):
        Params(command="echo test", timeout=MAX_TIMEOUT + 1)


@pytest.mark.asyncio
async def test_scan_annotation(config: Config, approval):
    config.cli_output.scan_tool_patterns = ["echo"]
    with tool_call_context("Bash"):
        bash_tool = Bash(approval, config)
        result = await bash_tool(Params(command="echo hello"))

    assert isinstance(result, ToolOk)
    lines = _transcript_lines(result.output)
    _assert_header(lines, "echo hello", scan=True)
    assert _body_contains(lines, "hello")
