# Proposal: Memory Footprint Optimization

## Change ID
optimize-memory-usage

## Summary
Reduce baseline memory usage by paginating history storage, streaming large artifacts instead of
loading them wholesale, and tightening caches so the CLI no longer keeps entire sessions or files in
RAM when only small windows are needed.

## Why
- The shell currently loads the entire conversation history and large files into memory, but only
  ~4.5% of the data is actively referenced.
- Long-lived sessions leak memory because buffers never evict older entries.
- Users on resource-constrained machines hit swapping or OOM when the agent reviews big repos.

## What Changes
- Replace the existing in-memory history store with a paginated backend (e.g., SQLite or mmap-backed
  log) that loads only the most recent N entries.
- Stream large workspace files using iterators/generators and apply mmap where appropriate, so
  commands operate on slices rather than full copies.
- Introduce configurable caps for caches/buffers plus telemetry to warn when memory usage approaches
  limits.

## Impact
- Dramatically lower peak memory while preserving recent history for UX features (autocomplete,
  replay).
- Enables stable behavior for hour-long sessions and large repository analyses.
- Slight increase in code complexity due to pagination and streaming abstractions.

## Open Questions
1. Which backing store (SQLite vs. LMDB vs. mmap files) offers the best balance for history paging?
2. Do we expose user controls for "recent history window" size or auto-tune based on available RAM?
