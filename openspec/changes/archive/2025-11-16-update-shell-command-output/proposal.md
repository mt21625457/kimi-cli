# Proposal: Structured Shell Command Summaries

## Change ID
update-shell-command-output

## Summary
Adopt a consistent, bullet-style transcript for every Bash tool invocation so users immediately see
what command ran, whether it produced output, and if it belonged to a pre-defined "scan" toolset.
This mirrors Codex CLI formatting, improving readability across shell, print, and ACP modes.

## Why
- Current Bash output streams raw stdout/stderr, which buries actual commands and makes transcripts
  hard to skim when dozens of calls occur per step.
- Security reviews and auditing require a quick way to see every command plus whether it was a
  scanner/security tool versus a routine operation.
- Users explicitly requested parity with OpenAI Codex CLI summaries to keep agent interactions
  predictable across tools.

## What Changes
- Introduce a formatter that captures `• Ran <command>` headers, pipes captured output through `│`
  prefixed lines, and terminates blocks with `└ (no output)` or explicit status text.
- Allow the formatter to detect commands that match a configurable scanning-tool allowlist, adding
  inline `(scan)` annotations so they stand out in transcripts.
- Update Bash tool execution to buffer stdout/stderr, emit the formatted block on success/failure,
  and ensure print/ACP modes display the same structure.

## Impact
- Improves operator trust by making command history human-scannable and auditable.
- Slight memory overhead to buffer command output before printing, but capped by existing
  `ToolResultBuilder` limits.
- Minimal risk since formatting happens post-execution; no behavior change to the commands
  themselves.

## Open Questions
1. Should scan-tool patterns ship with sensible defaults (e.g., `scan`, `openspec`, `rg --files`)
   or be entirely user-configurable via config file?
2. Do we need opt-in truncation hints (e.g., `… +38 lines`) when output exceeds thresholds, or
   should we always show the first few lines plus counts?
