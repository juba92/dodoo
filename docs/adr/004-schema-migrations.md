# ADR-004: Schema Migrations — Custom Diff-and-Apply Runner

**Status**: Accepted | **Date**: 2026-06-06

## Context
Modules must install/upgrade their schemas automatically at load time.

## Decision
Custom MigrationRunner: compare Python field definitions to `information_schema.columns`; issue `ALTER TABLE ADD COLUMN` for additive changes; raise `SchemaConflictError` for destructive changes.

## Consequences
- No Alembic dependency or migration files in source control
- Python class is the single source of truth
- Destructive changes are explicit errors, not silent data loss
