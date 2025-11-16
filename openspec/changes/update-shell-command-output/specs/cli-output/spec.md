## ADDED Requirements

### Requirement: Structured Command Invocation Output
Kimi CLI MUST present each Bash tool invocation as a compact block that shows the command,
a limited preview of its output, and an explicit footer describing both the exit status and
whether any output was produced.

#### Scenario: Rendered command with output preview
- **WHEN** the Bash tool finishes running `cat <<'EOF' > sample.txt` and captures stdout/stderr text
- **THEN** the transcript MUST start with `• Ran cat <<'EOF' > sample.txt`
- **AND** every captured output line MUST be prefixed by `│ ` with trailing `… +N lines` when output
  exceeds the configured preview limit
- **AND** the block MUST end with `└ (exit 0, output truncated)` or a similarly structured footer
  that reports the exit status and whether truncation happened.

#### Scenario: Command with no output
- **WHEN** a Bash command (e.g., `mkdir -p reports`) exits without producing stdout/stderr
- **THEN** the transcript MUST include `└ (exit 0, no output)` immediately after the header to
  signal success without logs.

#### Scenario: Command failure formatting
- **WHEN** the Bash tool runs `rg --files` and the process exits with code `2`
- **THEN** the transcript MUST include the command header plus any captured output lines with `│`
  prefixes
- **AND** the footer MUST read `└ (exit 2, failed)` or equivalent wording that conveys the non-zero
  exit status.

### Requirement: Scan Tool Annotation
The CLI MUST annotate command headers when their base executable matches a configurable set of
security/scan tool identifiers.

#### Scenario: Scan command annotation
- **WHEN** the Bash tool runs `scan-project --all`
- **THEN** the command header MUST read `• Ran scan-project --all (scan)`
- **AND** the output block formatting MUST follow the Structured Command Invocation Output
  requirement so the annotation co-exists with log previews.

### Requirement: Scan Tool Configuration
Users MUST be able to adjust which commands count as scan tools via configuration.

#### Scenario: Custom scan pattern
- **WHEN** a user adds `openspec validate` to the scan-tool pattern list in their config
- **AND** the Bash tool later runs `openspec validate --strict`
- **THEN** the command header MUST display the `(scan)` annotation without requiring a code change.
