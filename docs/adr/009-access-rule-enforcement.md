# ADR-009: Access Rule Enforcement — Pre-Query Domain Injection

**Status**: Accepted | **Date**: 2026-06-06

## Context
ir.rule domains must restrict what records users can see/write.

## Decision
Before any `search()` / `write()` / `create()` / `unlink()`, load applicable ir.rule domains for (model, uid, operation) and AND-merge them into the query WHERE clause.

## Consequences
- Restricted records never loaded into memory (transparent, efficient)
- Transparent to callers — they see only allowed records
- Write denial raises AccessError before any DB write
