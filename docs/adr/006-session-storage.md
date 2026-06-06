# ADR-006: Session Storage — ir.session PostgreSQL Table

**Status**: Accepted | **Date**: 2026-06-06

## Context
Sessions must survive server restarts; no Redis in scope.

## Decision
Store sessions in `ir_session` table: token (VARCHAR 64, unique), user_id, expire_date.

## Consequences
- Sessions persist across restarts
- Expired session cleanup queryable via SQL
- No additional infrastructure dependency
