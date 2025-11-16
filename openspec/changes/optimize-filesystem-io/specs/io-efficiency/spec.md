## ADDED Requirements
### Requirement: Buffered Context Persistence
Context and history logs MUST write through a bounded in-memory buffer that flushes either when
full or after a short timeout so that rapid streaming output does not block on disk flushes.

#### Scenario: Batched flush on streaming output
- **GIVEN** the assistant streams multiple tokens per second for at least 500 ms
- **WHEN** the context persistence layer receives these chunks
- **THEN** it writes them into an in-memory buffer first
- **AND** flushes them to disk only when the buffer reaches the configured size or the flush timer
  fires (whichever happens first)
- **AND** no more than one flush occurs per 100 ms unless the buffer is explicitly flushed.

#### Scenario: Explicit flush for durability
- **GIVEN** a user triggers a manual save/export command
- **WHEN** the system handles the request
- **THEN** all buffered context/history data is flushed immediately before the command completes.

### Requirement: Chunked Large File Reads
File tools that read workspace files MUST process them in chunks (configurable, default ≥64 KiB)
so that inspecting large files does not require loading them entirely into memory or issuing
per-line syscalls.

#### Scenario: Read API returns chunks
- **GIVEN** a user runs a read/grok command on a file larger than 10 MiB
- **WHEN** the tool streams the file to the agent
- **THEN** it iterates over chunk-sized buffers (e.g., 64 KiB) and yields them sequentially without
  loading the entire file at once.

### Requirement: Batched Appends For Logs
When appending to log-like artifacts (conversation history, tool transcripts), the system MUST
coalesce multiple append operations into a single write syscall whenever the combined payload is
smaller than the configured buffer size.

#### Scenario: Multiple appends collapse into one write
- **GIVEN** three log entries totaling less than the buffer capacity arrive within 50 ms
- **WHEN** they are written to the history file
- **THEN** the buffered writer emits a single write syscall containing all three entries instead of
  three separate writes.
