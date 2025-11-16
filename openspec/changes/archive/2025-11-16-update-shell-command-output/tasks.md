## 1. Research & Design
- [x] 1.1 Confirm all UI modes (shell, print, ACP) rely on the same Bash tool output path.
- [x] 1.2 Define default scan-tool patterns and configuration override strategy.

## 2. Implementation
- [x] 2.1 Add a formatting helper that renders command headers, indented output lines, truncation
        notices, and `(scan)` annotations when needed.
- [x] 2.2 Update Bash tool to buffer stdout/stderr, call the helper, and include explicit success or
        failure status in the footer line.
- [x] 2.3 Ensure Task/subagent logs preserve the formatted block when Bash runs inside subagents.
- [x] 2.4 Wire scan-tool configuration by loading default patterns, applying user overrides, and
        feeding the merged list to the formatter.

## 3. Tests & Docs
- [x] 3.1 Extend unit tests to cover plain commands, scan-tagged commands, and no-output cases.
- [x] 3.2 Update AGENTS/README docs with the new transcript style and guidance on configuring
        scan-tool detection.
