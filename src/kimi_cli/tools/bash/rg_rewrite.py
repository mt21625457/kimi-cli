from __future__ import annotations

import shlex
from dataclasses import dataclass, field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.utils.logging import logger
from kimi_cli.tools.ripgrep import (
    RipgrepAvailabilityError,
    describe_manual_installation,
    ensure_ripgrep_path,
    ensure_supported_grep_binary,
)


@dataclass(frozen=True)
class RewriteResult:
    """Result of attempting to rewrite a Bash command."""

    command_to_run: str
    display_command: str
    annotation: str | None = None
    original_command: str | None = None
    prologue_lines: list[str] = field(default_factory=list)
    footer_hint: str | None = None


_SEPARATORS = {"|", "||", "&&", ";", "&"}
_ASSIGNMENT_PREFIX = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_BOOL_FLAG_MAP = {
    "-n": "--line-number",
    "-i": "--ignore-case",
    "-v": "--invert-match",
    "-w": "--word-regexp",
}
_CONTEXT_FLAG_MAP = {
    "-A": "--after-context",
    "-B": "--before-context",
    "-C": "--context",
}
_UNSUPPORTED_TOKENS = ("$(", "`", ")>", "<(")


async def rewrite_command_if_needed(
    command: str,
    config: Config,
    approval: Approval,
) -> RewriteResult:
    stripped = command.strip()
    if not stripped:
        return RewriteResult(command_to_run=command, display_command=command)

    if not config.cli_output.replace_grep_with_rg:
        return RewriteResult(command_to_run=command, display_command=command)

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        logger.warning("grep rewrite skipped: failed to parse command", command=command)
        return RewriteResult(command_to_run=command, display_command=command)

    parts = _tokens_to_parts(tokens)
    if not parts:
        return RewriteResult(command_to_run=command, display_command=command)

    rewrote = False
    prologue_lines: list[str] = []
    for part in parts:
        if isinstance(part, _Operator):
            continue
        rewrite = await _rewrite_simple_command(part.tokens)
        if rewrite.applied:
            part.tokens = rewrite.tokens
            rewrote = True
        elif rewrite.reason:
            snippet = shlex.join(part.tokens)
            logger.warning(
                "grep rewrite skipped: {reason} ({command})",
                reason=rewrite.reason,
                command=snippet,
            )
            prologue_lines.append(f"rewrite skipped: {rewrite.reason}")

    if not rewrote:
        if prologue_lines:
            return RewriteResult(
                command_to_run=command,
                display_command=command,
                prologue_lines=prologue_lines,
            )
        return RewriteResult(command_to_run=command, display_command=command)

    try:
        await ensure_ripgrep_path(config, approval)
    except RipgrepAvailabilityError as exc:
        manual_hint = describe_manual_installation()
        message = f"ripgrep unavailable: {exc}. {manual_hint}"
        logger.warning(message)
        prologue_lines.append(message)
        return RewriteResult(
            command_to_run=command,
            display_command=command,
            prologue_lines=prologue_lines,
        )

    new_command = _render_parts(parts)
    prologue_with_original = [f"original: {command}"]
    prologue_with_original.extend(prologue_lines)
    return RewriteResult(
        command_to_run=new_command,
        display_command=new_command,
        original_command=command,
        annotation="auto-rewritten",
        prologue_lines=prologue_with_original,
        footer_hint="disable via cli_output.replace_grep_with_rg",
    )


class _Operator:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _SimpleCommand:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens


def _tokens_to_parts(tokens: list[str]) -> list[_Operator | _SimpleCommand]:
    parts: list[_Operator | _SimpleCommand] = []
    current: list[str] = []
    for token in tokens:
        if token in _SEPARATORS:
            if current:
                parts.append(_SimpleCommand(current.copy()))
                current.clear()
            parts.append(_Operator(token))
        else:
            current.append(token)
    if current:
        parts.append(_SimpleCommand(current.copy()))
    return parts


def _render_parts(parts: list[_Operator | _SimpleCommand]) -> str:
    rendered: list[str] = []
    for part in parts:
        if isinstance(part, _Operator):
            rendered.append(part.symbol)
        else:
            rendered.append(shlex.join(part.tokens))
    return " ".join(rendered).strip()


def _looks_like_assignment(token: str) -> bool:
    if "=" not in token:
        return False
    first = token.split("=", 1)[0]
    if not first:
        return False
    return first[0] in _ASSIGNMENT_PREFIX


def _contains_unsupported_token(tokens: list[str]) -> bool:
    for token in tokens:
        if any(marker in token for marker in _UNSUPPORTED_TOKENS):
            return True
    return False


class _SegmentRewrite:
    def __init__(self, applied: bool, tokens: list[str], reason: str | None = None):
        self.applied = applied
        self.tokens = tokens
        self.reason = reason


async def _rewrite_simple_command(tokens: list[str]) -> _SegmentRewrite:
    if not tokens:
        return _SegmentRewrite(False, tokens)

    if _contains_unsupported_token(tokens):
        return _SegmentRewrite(False, tokens, "detected unsupported bash substitution")

    prefix: list[str] = []
    idx = 0
    while idx < len(tokens) and _looks_like_assignment(tokens[idx]):
        prefix.append(tokens[idx])
        idx += 1

    if idx >= len(tokens):
        return _SegmentRewrite(False, tokens)

    cmd = tokens[idx]
    if cmd not in {"grep", "egrep", "fgrep"}:
        return _SegmentRewrite(False, tokens)

    if not await ensure_supported_grep_binary(cmd):
        return _SegmentRewrite(False, tokens, "detected non-GNU grep binary")

    args = tokens[idx + 1 :]
    parsed = _parse_grep_args(cmd, args)
    if parsed is None:
        return _SegmentRewrite(False, tokens, "unsupported grep arguments")

    new_tokens = prefix + parsed
    return _SegmentRewrite(True, new_tokens)


def _parse_grep_args(cmd: str, args: list[str]) -> list[str] | None:
    rg_tokens: list[str] = ["rg"]

    if cmd == "fgrep":
        rg_tokens.append("--fixed-strings")

    pattern_entries: list[tuple[str, bool]] = []
    files: list[str] = []
    double_dash_for_files = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            double_dash_for_files = True
            i += 1
            break
        if arg in ("-R", "-r"):
            i += 1
            continue
        if arg in _BOOL_FLAG_MAP:
            rg_tokens.append(_BOOL_FLAG_MAP[arg])
            i += 1
            continue
        if arg in _CONTEXT_FLAG_MAP:
            if i + 1 >= len(args):
                return None
            rg_tokens.extend([_CONTEXT_FLAG_MAP[arg], args[i + 1]])
            i += 2
            continue
        if arg.startswith("-e") and arg != "-e":
            pattern_entries.append((arg[2:], True))
            i += 1
            continue
        if arg == "-e":
            if i + 1 >= len(args):
                return None
            pattern_entries.append((args[i + 1], True))
            i += 2
            continue
        if arg in ("--include", "--exclude"):
            if i + 1 >= len(args):
                return None
            pattern = args[i + 1]
            rg_tokens.extend(["--glob", pattern if arg == "--include" else f"!{pattern}"])
            i += 2
            continue
        if arg.startswith("--include="):
            rg_tokens.extend(["--glob", arg.split("=", 1)[1]])
            i += 1
            continue
        if arg.startswith("--exclude="):
            rg_tokens.extend(["--glob", f"!{arg.split('=', 1)[1]}"])
            i += 1
            continue
        if arg == "--color=never" or arg == "--color" and i + 1 < len(args) and args[i + 1] == "never":
            rg_tokens.append("--color=never")
            i += 2 if arg == "--color" else 1
            continue
        if arg in ("-F", "--fixed-strings"):
            if "--fixed-strings" not in rg_tokens:
                rg_tokens.append("--fixed-strings")
            i += 1
            continue
        if arg in ("-E", "--extended-regexp"):
            i += 1
            continue
        if arg.startswith("-"):
            return None
        break

    remainder = args[i:]
    if pattern_entries:
        files = remainder
    else:
        if not remainder:
            return None
        pattern_entries.append((remainder[0], False))
        files = remainder[1:]

    if not pattern_entries:
        return None

    if len(pattern_entries) == 1 and not pattern_entries[0][1]:
        rg_tokens.append(pattern_entries[0][0])
    else:
        for pattern, _ in pattern_entries:
            rg_tokens.extend(["-e", pattern])

    if files:
        if double_dash_for_files:
            rg_tokens.append("--")
        rg_tokens.extend(files)

    return rg_tokens
