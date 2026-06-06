# ADR-002: Async Database Driver — asyncpg via SA2

**Status**: Accepted | **Date**: 2026-06-06

## Context
FastAPI is async; the driver must not block the event loop.

## Decision
asyncpg integrated via `create_async_engine("postgresql+asyncpg://...")`.

## Consequences
- ~2× read throughput over psycopg3 in benchmarks
- Connection pooling and dialect managed by SQLAlchemy 2
