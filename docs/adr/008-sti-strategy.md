# ADR-008: Single-Table Inheritance — Discriminator Column (_type)

**Status**: Accepted | **Date**: 2026-06-06

## Context
Spec requires child models to share the parent's table (STI).

## Decision
Add `_type VARCHAR(128)` discriminator column to parent table. Registry injects `WHERE _type = 'child.name'` on child queries.

## Consequences
- One table, no JOINs for inheritance queries
- Child-specific columns added via ALTER TABLE ADD COLUMN at install time
- Parent queries return all rows (parent + child discriminated by _type)
