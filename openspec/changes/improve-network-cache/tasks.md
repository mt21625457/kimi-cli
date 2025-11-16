## 1. Implementation
- [ ] 1.1 Introduce a shared async HTTP client factory that manages keep-alive pools, retry/backoff,
      and TLS settings for all outbound requests.
- [ ] 1.2 Implement two-tier caching (in-memory LRU + optional disk cache) for high-churn read
      operations, with configurable TTLs and cache keys derived from request params.
- [ ] 1.3 Add instrumentation hooks (logging or metrics) to report connection pool usage, cache hits,
      and fallbacks when caches are bypassed.

## 2. Validation
- [ ] 2.1 Add integration tests or mocks verifying that repeated requests reuse the same client,
      respect TTLs, and serve cached data when appropriate.
- [ ] 2.2 Document new configuration flags (pool size, TTL, cache directory) and run `make check`
      / `make test` to confirm the changes pass CI gates.
