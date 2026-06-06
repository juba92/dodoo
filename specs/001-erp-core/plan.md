# Implementation Plan: Minimal ERP Core

**Branch**: `001-erp-core` | **Date**: 2026-06-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-erp-core/spec.md`

## Summary

Build a minimal Odoo-inspired ERP core in Python: a custom declarative ORM with a model
registry backed by SQLAlchemy Core 2.0, a plugin-based module loader using Python's stdlib
`graphlib.TopologicalSorter`, a FastAPI HTTP layer exposing JSON-RPC 2.0 and a REST route
registry, and session-based authentication with group/rule-driven row-level access control.
All subsystems are importable as a library and can be tested without starting the HTTP server.
Target: single-tenant local PostgreSQL 15, single ASGI process, no UI.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**:
- FastAPI 0.111 (ASGI framework + REST routing)
- SQLAlchemy 2 Core (DDL + parameterised query building, async engine)
- asyncpg (async PostgreSQL driver via SA2 async engine)
- Pydantic v2 (request/response validation at HTTP boundary)
- argon2-cffi (Argon2id password hashing)
- Python stdlib: `graphlib.TopologicalSorter`, `importlib`, `secrets`

**Dev / Test Dependencies**:
- pytest, pytest-asyncio
- testcontainers-python (PostgreSQL container for integration tests)
- httpx (async test client for FastAPI)
- ruff (linting + formatting)

**Storage**: PostgreSQL 15 (single database, `public` schema)

**Testing**: pytest + pytest-asyncio + testcontainers; coverage enforced via pytest-cov

**Target Platform**: Linux, single ASGI process (uvicorn), localhost only

**Project Type**: library + web-service (importable as `dodoo`, launchable as `python -m dodoo server`)

**Performance Goals**:
- ORM single-record lookup by ID: p95 < 10ms (100k-row table, local PostgreSQL)
- HTTP JSON-RPC throughput: ≥ 200 req/s sustained (single process, localhost)
- Module load: < 5s for 10 modules × 5 models on first install

**Constraints**: Single-tenant, no TLS, no multi-tenancy, no UI, no horizontal scaling,
destructive schema migrations deferred to a future milestone.

**Scale/Scope**: Single company, single process, extensible add-on ecosystem.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Code Quality**: ruff configured for linting and formatting; naming follows Python
      PEP 8 + project conventions; CI enforces zero lint errors.
- [x] **II. Testing**: ≥ 80% unit coverage enforced by pytest-cov in CI; integration tests cover
      all DB paths with real PostgreSQL (testcontainers); e2e tests cover all user journeys.
      No silent mocks: testcontainers used for DB, httpx AsyncClient for HTTP.
- [x] **III. Security**: OWASP Top 10 checklist required per subsystem; parameterised queries via
      SQLAlchemy Core (no string interpolation); Argon2id for passwords; cryptographically
      random session tokens (secrets.token_urlsafe); least-privilege DB credentials in prod.
- [x] **IV. Performance**: ORM, HTTP, and module-load targets defined above; benchmark tests for
      ORM lookup and JSON-RPC throughput must run in CI; 10% regression threshold enforced.
- [x] **V. Documentation**: ADR required for each architectural decision (9 decisions resolved in
      research.md); inline comments WHY-only; no docstring bloat.
- [x] **VI. Accessibility**: No UI in this milestone — accessibility gate is N/A; re-evaluate
      if a UI milestone is added.
- [x] **VII. Dependencies**: All dependencies pinned in `pyproject.toml` with lock file
      (`pip-audit` in CI; no unused deps; licenses verified: MIT/Apache-2.0).
- [x] **VIII. CI/CD**: CI gates: ruff lint + format, unit tests + coverage ≥ 80%, integration
      tests, e2e tests, pip-audit; `--no-verify` prohibited; branch protection required.
- [x] **IX. Observability**: Structured JSON logging with `correlation_id` on every request;
      health check endpoint; all exceptions logged with traceback at ERROR level before
      returning a sanitised error response.

*Post-design re-check*: All gates pass. No violations. No complexity justification required.

## Project Structure

### Documentation (this feature)

```text
specs/001-erp-core/
├── plan.md              # This file
├── research.md          # Phase 0 — all technology decisions
├── data-model.md        # Phase 1 — schema, entities, state machines
├── quickstart.md        # Phase 1 — validation guide
└── contracts/
    ├── jsonrpc.md       # JSON-RPC 2.0 endpoint contract
    └── rest-routing.md  # REST route registry contract
```

### Source Code (repository root)

```text
dodoo/                          # main library package
├── __init__.py                 # exports Environment, BaseModel
├── core/
│   ├── __init__.py
│   ├── registry.py             # ModelRegistry: register, lookup, inheritance
│   ├── fields.py               # Field types: Char, Integer, Many2one, etc.
│   ├── models.py               # BaseModel metaclass + CRUD methods
│   ├── query.py                # domain filter → SQLAlchemy WHERE compiler
│   └── migration.py            # schema diff-and-apply runner
├── modules/
│   ├── __init__.py
│   ├── loader.py               # add-on discovery + topological sort
│   └── installer.py            # install / upgrade orchestrator
├── http/
│   ├── __init__.py
│   ├── app.py                  # FastAPI app factory
│   ├── jsonrpc.py              # /jsonrpc dispatcher (service → method table)
│   ├── routing.py              # REST route registry (@http.route decorator)
│   └── middleware.py           # session auth middleware + correlation ID injection
├── auth/
│   ├── __init__.py
│   ├── session.py              # session create / validate / invalidate
│   └── access.py               # ir.rule loader + domain injection
├── addons/
│   └── base/
│       ├── __manifest__.py     # {"name": "base", "version": "1.0", "depends": []}
│       ├── models/
│       │   ├── __init__.py
│       │   ├── res_users.py    # res.users model
│       │   ├── res_groups.py   # res.groups model
│       │   ├── ir_rule.py      # ir.rule model
│       │   └── ir_session.py   # ir.session model
│       └── data/
│           └── base_data.py    # seed: admin user, base groups
└── __main__.py                 # entry point: python -m dodoo server

tests/
├── conftest.py                 # DB fixture (testcontainers PostgreSQL)
├── unit/
│   ├── test_fields.py          # field type definitions and metadata
│   ├── test_registry.py        # model registration, STI, name conflicts
│   ├── test_query.py           # domain filter compiler: operators, logic, edge cases
│   └── test_loader.py          # topological sort, cycle detection, manifest parsing
├── integration/
│   ├── test_orm_crud.py        # create/read/update/delete + Many2one FK enforcement
│   ├── test_migrations.py      # additive migration, destructive migration raises error
│   ├── test_access_rules.py    # ir.rule domain injection, write denial
│   └── test_http_jsonrpc.py    # JSON-RPC 2.0 full round-trip, error envelopes, auth
└── e2e/
    └── test_full_flow.py       # install add-on → CRUD via HTTP → logout

pyproject.toml                  # deps (pinned), ruff config, pytest config, coverage config
.env.example
```

**Structure Decision**: Single Python project with library core + built-in add-ons under
`dodoo/addons/`. Tests mirror the source structure with unit / integration / e2e layers.
No separate backend/frontend split (no UI in this milestone).

## Complexity Tracking

No constitution violations. No complexity justification required.
