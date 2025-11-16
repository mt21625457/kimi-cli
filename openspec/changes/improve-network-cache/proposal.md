# Proposal: Network & Cache Efficiency

## Change ID
improve-network-cache

## Summary
Rework outbound HTTP usage so tools share persistent connection pools and introduce layered caching
for repeatable lookups (search results, file metadata). This reduces the 1.6s baseline delay on
search-oriented commands and cuts bandwidth usage for repeated queries.

## Why
- Each Bash/search tool invocation currently spins up a new HTTP client, paying TLS setup costs and
  wasting CPU time.
- Lack of caching means repeated searches or metadata fetches hit third-party APIs even when the
  inputs have not changed within minutes.
- Users experience sluggish agent responses when subagents queue multiple web requests back-to-back.

## What Changes
- Provide a singleton async HTTP client (per base URL) with keep-alive and bounded connection pools,
  plus automatic retries and timeouts.
- Layer in-memory LRU and optional disk caches for read-mostly APIs (Moonshot search, file listing,
  docs fetch) with short TTLs to avoid stale data.
- Expose instrumentation so developers can inspect cache hit rates and pool utilization.

## Impact
- Expect 200–400 ms savings per external request thanks to connection reuse.
- Backend APIs experience fewer redundant requests, lowering rate-limit pressure.
- Slight increase in complexity due to cache invalidation and telemetry plumbing.

## Open Questions
1. Should cache TTLs be user-configurable per tool, or governed by a single global policy?
2. Do we need opt-out switches for users on sensitive networks who prefer no caching?
