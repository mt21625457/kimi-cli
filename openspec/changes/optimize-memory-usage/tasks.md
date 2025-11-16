## 1. Implementation
- [ ] 1.1 Introduce a paginated history store (SQLite/mmap) with APIs to fetch the most recent N
      messages plus lazy iterators for older entries when needed.
- [ ] 1.2 Update file inspection/analysis helpers to stream data via generators or mmap slices
      instead of loading full files into memory.
- [ ] 1.3 Add configuration and telemetry for memory caps (history window size, max buffer bytes)
      plus warnings when usage nears the cap.

## 2. Validation
- [ ] 2.1 Create tests that simulate long sessions and large file inspections, asserting the new
      store stays within configured memory budgets.
- [ ] 2.2 Document operating guidance (default window size, how to tune caps) and ensure `make
      check` / `make test` pass.
