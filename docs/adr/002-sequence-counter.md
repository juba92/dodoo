# ADR-002: Application-Level Sequence Counter Table

**Status**: Accepted | **Date**: 2026-06-07

## Context

Journal entries need unique sequential reference numbers per journal per year (e.g. INV/2026/0001). These must be gap-free after posting and collision-free under concurrency.

## Decision

A dedicated `account_sequence` table with columns `(prefix VARCHAR(32), year INTEGER, last_no INTEGER, PRIMARY KEY(prefix, year))` is used. Sequence numbers are assigned via atomic upsert:

```sql
INSERT INTO account_sequence (prefix, year, last_no) VALUES (:p, :y, 1)
ON CONFLICT (prefix, year) DO UPDATE SET last_no = account_sequence.last_no + 1
RETURNING last_no;
```

## Consequences

- No DDL at runtime — only DML privileges needed on the app DB user (least-privilege, ADR-001 alignment).
- The upsert is atomic per row; concurrent sessions cannot produce duplicate numbers.
- Once a number is assigned at posting, resetting to draft preserves the gap (FR-013).
- PostgreSQL native SEQUENCE objects were rejected because they require DDL privileges and one object per (journal, year) combination.
