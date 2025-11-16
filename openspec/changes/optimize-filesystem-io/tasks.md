## 1. Implementation
- [ ] 1.1 Design and implement a buffered I/O helper that supports chunked reads, write-behind
      buffers, flush intervals, and emergency flush hooks.
- [ ] 1.2 Refactor context persistence and conversation history writers to consume the helper,
      adding configuration for buffer size and flush cadence.
- [ ] 1.3 Update file tooling (read/write/patch utilities) to use chunked processing when touching
      large files, and surface metrics for flush counts/latency in debug logs.

## 2. Validation
- [ ] 2.1 Add benchmarks or pytest-based timing assertions covering large read/write scenarios to
      prove buffered paths outperform the old per-line approach.
- [ ] 2.2 Document new configuration knobs (buffer size, flush timeout) in README/AGENTS and ensure
      `make check` / `make test` pass.
