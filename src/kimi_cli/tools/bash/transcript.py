from __future__ import annotations

from kimi_cli.tools.utils import DEFAULT_MAX_LINE_LENGTH, truncate_line

ELLIPSIS = "…"
PREVIEW_LINE_LIMIT = 20
TRUNCATE_MARKER = "[...truncated]"


class CommandOutputCollector:
    """Collects command output for later transcript formatting."""

    def __init__(self, preview_line_limit: int = PREVIEW_LINE_LIMIT):
        self._preview_line_limit = preview_line_limit
        self._preview_lines: list[str] = []
        self._hidden_line_count = 0
        self._has_output = False
        self._line_truncated = False

    def add_line(self, line: str) -> None:
        """Record a decoded stdout/stderr line."""
        if not line:
            return

        self._has_output = True
        truncated_line = truncate_line(line, DEFAULT_MAX_LINE_LENGTH, TRUNCATE_MARKER)
        if truncated_line != line:
            self._line_truncated = True

        if len(self._preview_lines) < self._preview_line_limit:
            self._preview_lines.append(truncated_line)
        else:
            self._hidden_line_count += 1

    @property
    def preview_lines(self) -> list[str]:
        return self._preview_lines

    @property
    def hidden_line_count(self) -> int:
        return self._hidden_line_count

    @property
    def has_output(self) -> bool:
        return self._has_output

    @property
    def is_truncated(self) -> bool:
        return self._hidden_line_count > 0 or self._line_truncated


def format_transcript(
    command: str,
    collector: CommandOutputCollector,
    *,
    exit_code: int | None,
    is_scan: bool,
    timeout: int | None = None,
) -> str:
    """Format a command transcript block."""
    lines: list[str] = []
    header = f"• Ran {command}"
    if is_scan:
        header += " (scan)"
    lines.append(header)

    for preview_line in collector.preview_lines:
        if preview_line:
            lines.append(f"  │ {preview_line}")
        else:
            lines.append("  │ ")

    if collector.hidden_line_count:
        lines.append(f"  │ {ELLIPSIS} +{collector.hidden_line_count} lines")

    footer_parts: list[str] = []
    if exit_code is not None:
        footer_parts.append(f"exit {exit_code}")
        if exit_code != 0:
            footer_parts.append("failed")
    elif timeout is not None:
        footer_parts.append(f"timeout ({timeout}s)")
    else:
        footer_parts.append("terminated")

    if not collector.has_output and "no output" not in footer_parts:
        footer_parts.append("no output")

    if collector.is_truncated and "output truncated" not in footer_parts:
        footer_parts.append("output truncated")

    lines.append(f"  └ ({', '.join(footer_parts)})")
    return "\n".join(lines) + "\n"
