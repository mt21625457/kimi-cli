## ADDED Requirements
### Requirement: Export Session Transcript On Demand
The CLI MUST let users export the current session transcript to a Markdown or JSON file via a shell
command or Print mode flag.

#### Scenario: User exports transcript from Shell UI
- **GIVEN** a user is in an active Kimi CLI Shell session
- **WHEN** they run the `export-transcript --format markdown --output logs/` command
- **THEN** the CLI writes a Markdown file under `logs/` containing the entire conversation history
  in chronological order
- **AND** the command exits with a success status and prints the output path

#### Scenario: Non-interactive export flag
- **GIVEN** a user runs `kimi --print --export-transcript transcript.json`
- **WHEN** the run completes
- **THEN** the CLI writes `transcript.json` in JSON format with the full transcript payload.

### Requirement: Transcript Metadata Completeness
Transcript files MUST capture the information needed to audit or replay an interaction, including
messages, tool invocations, timestamps, and token usage summaries.

#### Scenario: Tool call metadata preserved
- **GIVEN** at least one tool (e.g., bash) ran during the session
- **WHEN** the transcript is exported
- **THEN** the file includes the tool name, arguments, start/end timestamps, and summarized
  stdout/stderr
- **AND** user/assistant turns reference tool call outcomes.

#### Scenario: Token accounting recorded
- **GIVEN** the LLM backend provides token usage numbers
- **WHEN** the transcript is exported
- **THEN** the transcript includes request/response token counts per turn and aggregated totals.

### Requirement: Sensitive Data Redaction
Exported transcripts MUST redact secrets (API keys, access tokens, env vars tagged as secrets) before
writing to disk.

#### Scenario: Secret values removed
- **GIVEN** the context contains `${KIMI_API_KEY}` or other marked secrets
- **WHEN** the transcript is exported
- **THEN** those values are replaced with `[REDACTED]`
- **AND** the file never stores raw secret material.
