# ADR-007: JSON-RPC Dispatch — Custom FastAPI Endpoint + Dispatch Table

**Status**: Accepted | **Date**: 2026-06-06

## Context
Third-party jsonrpcserver is sync-only and incompatible with FastAPI async.

## Decision
Custom `POST /jsonrpc` handler with an internal `(service, method) → async callable` dispatch table.

## Consequences
- Full control over session injection and error formatting
- ~150 lines of code; no external JSON-RPC framework dependency
- Error codes -32700 to -32603 and -32000 all custom-handled
