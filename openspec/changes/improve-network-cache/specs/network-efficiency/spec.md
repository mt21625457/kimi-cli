## ADDED Requirements
### Requirement: Shared HTTP Connection Pools
All networked tools MUST obtain HTTP clients from a shared pool that maintains persistent
connections, enforces per-host limits, and retries transient failures.

#### Scenario: Reuse existing connection
- **GIVEN** the agent issues two search requests to the same base URL within 60 seconds
- **WHEN** the second request is dispatched
- **THEN** it reuses an existing keep-alive connection from the pool instead of creating a new TCP
  session
- **AND** pool limits prevent unbounded concurrent connections.

### Requirement: Layered Response Caching
Frequently repeated read operations (search results, file metadata, docs fetches) MUST leverage an
in-memory LRU cache backed by an optional on-disk cache with configurable TTLs.

#### Scenario: Cache hit short-circuits remote call
- **GIVEN** a search query identical to one executed within the last N minutes (TTL)
- **WHEN** the agent handles the query again
- **THEN** it serves the response from cache immediately
- **AND** logs note the cache hit.

#### Scenario: TTL expiry forces refresh
- **GIVEN** a cached entry whose TTL has elapsed
- **WHEN** the same request is repeated
- **THEN** the system bypasses cache, re-fetches fresh data, and stores it again.

### Requirement: Instrumentation & Opt-Out Controls
The system MUST expose diagnostics about cache hit rates and pool usage, and allow users to disable
caching or pooling via configuration.

#### Scenario: User disables caching
- **GIVEN** a user sets `caching.enabled = false`
- **WHEN** the agent handles requests
- **THEN** it skips both in-memory and disk caches while still honoring connection pooling.

#### Scenario: Pool metrics surfaced
- **GIVEN** verbose logging is enabled
- **WHEN** the connection pool scales up or reuses connections
- **THEN** logs include debug entries summarizing pool size, idle connections, and reuse counts.
