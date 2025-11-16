## ADDED Requirements
### Requirement: Paginated History Storage
The CLI MUST store conversation history in a paginated backend that only loads the most recent N
entries into memory at any time, while allowing lazy access to older turns.

#### Scenario: Limited in-memory history window
- **GIVEN** the configured history window is 200 turns
- **WHEN** a session exceeds 200 turns
- **THEN** only the latest 200 turns reside in memory
- **AND** older turns are fetched on demand when scrolling or exporting.

### Requirement: Streaming File Inspection
File inspection/analysis helpers MUST operate on streaming iterators or memory-mapped slices so that
large files (≥10 MiB) are never fully loaded into RAM.

#### Scenario: Analyze large file with constant memory
- **GIVEN** the agent inspects a 200 MiB log file
- **WHEN** it scans for patterns
- **THEN** peak memory usage remains within the configured buffer cap because the file is processed
  chunk by chunk.

### Requirement: Memory Caps & Telemetry
The system MUST expose configuration for memory usage caps (history window, buffer bytes) and emit
telemetry or warnings when actual usage nears those caps.

#### Scenario: Warning when cap approached
- **GIVEN** the history window uses 90% of its configured memory budget
- **WHEN** additional turns arrive
- **THEN** the CLI logs a warning or toast prompting the user to increase the cap or export data.
