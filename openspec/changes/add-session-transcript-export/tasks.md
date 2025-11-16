## 1. Implementation
- [ ] 1.1 Add context serialization helpers that produce a transcript payload with messages, tool
      calls, token counts, and timestamps (ensure secrets are redacted).
- [ ] 1.2 Implement CLI entry points (Shell command + Print mode flag) that call the export helper
      and write Markdown/JSON files under the workspace.
- [ ] 1.3 Document configuration knobs (default export location, filename pattern, format) and wire
      them into `~/.kimi/config.json` loading.

## 2. Validation
- [ ] 2.1 Add pytest coverage that fakes a conversation and asserts the exported transcript matches
      spec scenarios.
- [ ] 2.2 Run `make check` and `make test` to ensure regressions are caught.
