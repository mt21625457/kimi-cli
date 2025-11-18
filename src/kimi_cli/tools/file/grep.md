A powerful search tool based-on ripgrep.

**Tips:**
- Prefer the Grep tool over invoking `grep` in the Bash tool. Bash will auto-rewrite simple
  `grep`/`egrep`/`fgrep` pipelines to ripgrep (`rg`), but this tool already exposes idiomatic
  ripgrep options and richer output modes.
- Use the ripgrep pattern syntax, not grep syntax. E.g. you need to escape braces like `\\{` to search for `{`.
- If `rg` is missing, the CLI can download and verify an official build into `~/.kimi/bin`. The
  download requires approval unless `cli_output.auto_install_ripgrep` is `true`.
