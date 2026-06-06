# Research: Minimal ERP Core

**Feature**: `001-erp-core` | **Date**: 2026-06-06

All unknowns from the Technical Context are resolved below. Each entry records the decision,
rationale, and alternatives rejected.

---

## 1. ORM Foundation

**Decision**: SQLAlchemy Core 2.0 (not the ORM layer; not raw asyncpg)

**Rationale**: SQLAlchemy Core gives us type-safe DDL construction (`Table`, `Column`, typed
column types), parameterised query building (preventing SQL injection automatically), and DDL
introspection — without the ActiveRecord-style Session/ORM that would conflict with our own
custom declarative model registry. We build our `BaseModel` metaclass on top of Core, keeping
full control over the field system.

**Alternatives rejected**:
- *Raw asyncpg*: gives speed but requires hand-writing all DDL strings and parameterisation;
  fragile for schema introspection and multi-type support.
- *SQLAlchemy ORM*: its own declarative base conflicts with our Odoo-style registry; adds
  identity map, session lifecycle, and lazy-loading complexity we do not want.

---

## 2. Async Database Driver

**Decision**: asyncpg, integrated via SQLAlchemy 2's `create_async_engine("postgresql+asyncpg://...")`

**Rationale**: asyncpg is the fastest PostgreSQL async driver (native binary protocol, no ORM
overhead). SQLAlchemy 2's async engine wraps asyncpg with connection pooling, dialect
translation, and cursor lifecycle management that integrates cleanly with FastAPI's event loop.

**Alternatives rejected**:
- *psycopg3 async*: valid choice; asyncpg chosen for throughput advantage (~2× faster for
  read-heavy workloads in benchmarks). psycopg3 may be revisited if COPY or LISTEN/NOTIFY
  is needed in a future milestone.

---

## 3. Module / Plugin Loader

**Decision**: Python `importlib.import_module` for package loading + `graphlib.TopologicalSorter`
(stdlib, Python 3.9+) for dependency resolution

**Rationale**: `graphlib.TopologicalSorter` raises `CycleError` on circular dependencies and
produces topologically sorted load order — exactly what we need. It is part of the Python
standard library (no extra dependency) and sufficient for directed acyclic graph ordering of
a module dependency graph.

**Alternatives rejected**:
- *networkx*: significant dependency weight for a single graph algorithm; overkill here.
- *Custom topological sort*: unnecessary when stdlib provides a well-tested implementation.

---

## 4. Schema Migration Strategy

**Decision**: Custom diff-and-apply runner (compare declared Python field definitions to
`information_schema.columns` at install time; issue `ALTER TABLE ADD COLUMN` for additive
changes; raise `SchemaConflictError` for destructive changes)

**Rationale**: Alembic is designed for human-authored migration scripts with an explicit
version history. Our model is "install/upgrade module → schema automatically applied" — a
code-first approach where the Python class *is* the source of truth. A custom runner reads
our `Field` objects, compares them to the live DB, and produces the minimal DDL diff. No
migration files in source control, no Alembic `env.py`.

**Alternatives rejected**:
- *Alembic autogenerate*: adds migration file directory, version table, and CLI; not
  compatible with our "import and go" philosophy.
- *Full schema drop-and-recreate*: destroys data; unacceptable for upgrades.

---

## 5. Password Hashing

**Decision**: `argon2-cffi` library, Argon2id algorithm

**Rationale**: Argon2id is OWASP's primary recommendation for new systems as of 2024. It is
memory-hard (resistant to GPU and ASIC brute-force attacks) and time-hard. `argon2-cffi` is
the mature, production-ready Python binding maintained by the Argon2 authors.

**Alternatives rejected**:
- *passlib[bcrypt]*: bcrypt is widely deployed and acceptable for legacy systems but is not
  memory-hard; Argon2id provides stronger security for new implementations.
- *hashlib PBKDF2*: weaker than Argon2id for password storage; OWASP lists it as third choice.

---

## 6. Session Storage

**Decision**: `ir.session` table in PostgreSQL (server-side, persistent)

**Rationale**: In-memory dict sessions are lost on server restart, making every restart a
forced logout for all users. A PostgreSQL table survives restarts, is introspectable for
debugging (expired session cleanup), and requires no additional infrastructure. Redis is
explicitly out of scope for this milestone.

**Alternatives rejected**:
- *In-memory dict*: sessions lost on restart.
- *Redis*: out of scope per spec assumptions.

---

## 7. JSON-RPC 2.0 Dispatch

**Decision**: Custom FastAPI `POST /jsonrpc` endpoint with an internal dispatch table mapping
`(service, method)` → `async callable`; no third-party JSON-RPC library

**Rationale**: `jsonrpcserver` and similar libraries are synchronous and do not integrate with
FastAPI's async dependency injection. A custom dispatcher is under 150 lines, gives full
control over session injection, error formatting, and async execution, and avoids a dependency
that requires monkey-patching for async support.

**Alternatives rejected**:
- *jsonrpcserver*: sync-only; incompatible with async FastAPI handlers.
- *fastapi-jsonrpc*: adds a framework layer over FastAPI that conflicts with our custom routing
  registry.

---

## 8. Single-Table Inheritance Strategy

**Decision**: Discriminator column (`_type VARCHAR`) on the parent model's table; child models
add their columns to the same table via `ALTER TABLE ADD COLUMN`; queries are filtered by
`_type` automatically by the registry.

**Rationale**: Matches the spec requirement ("shares its table, child-specific fields in
additional columns"). True STI: one table, one query, no joins. The discriminator column is
added automatically by the registry when a child model is registered.

**Alternatives rejected**:
- *Joined-table inheritance*: requires a JOIN for every query; spec says single-table.
- *Concrete-table inheritance*: each child gets its own table with duplicated parent columns;
  wastes schema space and makes polymorphic queries complex.

---

## 9. Access Rule Enforcement

**Decision**: Pre-query domain injection — before any ORM `search()` / `write()` / `create()`
/ `unlink()` call, load applicable `ir.rule` domains for the current user's groups and
operation; merge them into the query's `WHERE` clause before SQL is generated

**Rationale**: Server-side filtering at the SQL layer (not post-fetch in Python) ensures
restricted records are never loaded into memory, even accidentally. Transparent to callers:
they get back only what they are allowed to see.

**Alternatives rejected**:
- *Post-fetch Python filter*: restricted records are loaded into memory and then discarded;
  leaks data to the ORM layer; less efficient.
- *Database row-level security (RLS)*: requires per-user DB roles; conflicts with single
  shared connection pool and adds operational complexity beyond this milestone's scope.

---

## Summary of All Decisions

| Topic | Decision |
|-------|----------|
| ORM layer | SQLAlchemy Core 2.0 (no ORM) |
| Async driver | asyncpg via SA2 async engine |
| Module loader | importlib + graphlib.TopologicalSorter |
| Schema migrations | Custom diff-and-apply runner |
| Password hashing | argon2-cffi (Argon2id) |
| Session storage | ir.session PostgreSQL table |
| JSON-RPC dispatch | Custom FastAPI endpoint + dispatch table |
| STI strategy | Discriminator column (_type) |
| Access rule enforcement | Pre-query domain injection |
