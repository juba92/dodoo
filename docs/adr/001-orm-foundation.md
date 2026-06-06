# ADR-001: ORM Foundation — SQLAlchemy Core 2.0

**Status**: Accepted | **Date**: 2026-06-06

## Context
We need type-safe DDL, parameterised queries (SQL injection prevention), and schema introspection without the constraints of SQLAlchemy's ActiveRecord ORM.

## Decision
Use SQLAlchemy Core 2.0 only — no ORM/Session layer. Build a custom `BaseModel` metaclass on top.

## Consequences
- Full control over field system and query lifecycle
- No identity map, lazy loading, or session complexity
- Must implement CRUD methods manually (acceptable — this is the design goal)
