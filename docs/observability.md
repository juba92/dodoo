# Observability Guide

## Alert Surfaces

1. **ERROR log entries**: Every unhandled exception is logged at ERROR with full traceback
   and correlation_id. Monitor stdout/stderr for `"level": "ERROR"` JSON entries.

2. **`GET /web/health` returning 503**: Indicates database connectivity loss.
   Configure uptime monitoring to alert on HTTP 503 from this endpoint.

## Latency / Throughput
- CI benchmark gate: PERF-001 (p95 < 10ms), PERF-002 (≥200 req/s), PERF-003 (< 5s)
- A 10% regression from the stored baseline fails CI

## Correlation IDs
- Every request receives a UUID correlation_id injected by CorrelationMiddleware
- All log lines for a request share the same correlation_id for tracing
