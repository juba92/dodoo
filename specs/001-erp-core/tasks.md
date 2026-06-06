---
description: "Task list for Minimal ERP Core implementation"
---

# Tasks: Minimal ERP Core

**Input**: Design documents from `/specs/001-erp-core/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Tests**: Included — integration tests required by constitution (Principle II); unit tests for
all business logic; e2e for primary user journeys.

**Organization**: Tasks grouped by user story. Each story is independently completable and
testable. Tests are written before implementation within each story (TDD recommended).

**Revision note** (2026-06-06): Added T014 (bootstrap), T015 (meta-models), T057 (middleware
wiring); split old T037 into stub (T039) + wiring (T057); extended T059 with PERF-003
benchmark; fixed cross-references throughout. Addresses analysis findings C1, C2, H1, H3.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared state dependencies)
- **[Story]**: Which user story (US1 = Model Registry/ORM, US2 = Module Loader,
  US3 = HTTP Layer, US4 = Auth/Access Control)
- Exact file paths included in all descriptions

## Path Conventions

All source paths are relative to repository root. The main library package is `dodoo/`.
Tests live in `tests/` mirroring source structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding, tooling config, and CI pipeline. No user story can begin
without a working project structure.

- [ ] T001 Create Python project layout: `dodoo/`, `tests/unit/`, `tests/integration/`,
  `tests/e2e/`, `docs/adr/`, `dodoo/addons/base/` with `__init__.py` files in each package
- [ ] T002 Write `pyproject.toml`: declare dependencies (fastapi, sqlalchemy[asyncio], asyncpg,
  argon2-cffi, pydantic, uvicorn), dev deps (pytest, pytest-asyncio, pytest-cov,
  testcontainers, httpx, ruff, pip-audit), ruff config (line-length 100, isort, pyflakes),
  pytest config (asyncio_mode=auto, cov threshold 80%)
- [ ] T003 [P] Write `.env.example` with `DATABASE_URL`, `DATABASE_MIGRATION_URL`,
  `SESSION_EXPIRY_HOURS`, `ADDONS_PATH`, `LOG_LEVEL` (no real values — example only)
- [ ] T004 [P] Write `.github/workflows/ci.yml`: jobs for ruff lint, ruff format check,
  pytest unit + coverage gate (≥ 80%), pytest integration, pytest e2e, pip-audit (block
  on HIGH/CRITICAL); no `--no-verify` or skip-checks paths; pip-audit is the sole owner
  of CVE scanning in CI — do not duplicate in other tasks
- [ ] T005 [P] Write `dodoo/core/exceptions.py`: define base exception hierarchy —
  `DodooError`, `SchemaConflictError`, `ModuleLoadError`, `CycleError`, `AuthenticationError`,
  `AccessError`, `RouteConflictError`, `DomainError`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared runtime infrastructure that every user story depends on. Includes the
bootstrap sequence that creates core registry tables before any module can be installed.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [ ] T006 Implement `dodoo/core/db.py`: async SQLAlchemy engine factory
  `create_engine(database_url)` returning an `AsyncEngine`; expose `get_connection()` async
  context manager; read `DATABASE_URL` (DML) and `DATABASE_MIGRATION_URL` (DDL) from
  environment; use asyncpg dialect; on connection failure raise `DodooError('Database
  unavailable')` which HTTP layer maps to 503 / JSON-RPC `-32603`
- [ ] T007 [P] Implement `dodoo/core/logging.py`: configure structlog (or stdlib logging with
  JSON formatter) to emit `{"timestamp", "level", "service": "dodoo", "correlation_id",
  "message"}` on every log call; expose `get_logger(name)` helper; `DEBUG` disabled when
  `LOG_LEVEL != DEBUG`
- [ ] T008 [P] Write `tests/conftest.py`: pytest fixture `pg_engine` that spins up a
  PostgreSQL 15 testcontainer, yields an `AsyncEngine`, and tears down after the test session;
  fixture `env` that returns a live `Environment` connected to the test DB; add assertion
  that each test request produces a non-empty `correlation_id` in captured log records
- [ ] T009 Verify structured logging integration: write a single unit test in
  `tests/unit/test_logging.py` that asserts `get_logger()` produces JSON-compatible output
  containing all required fields; confirm `correlation_id` defaults to empty string when no
  request context is active (not a missing key)
- [ ] T010 [P] Declare `pip-audit` in dev deps section of `pyproject.toml`; document approved
  licenses (MIT, Apache-2.0, BSD, PSF) in `pyproject.toml` `[tool.licenses]` table;
  note: CI integration is owned by T004
- [ ] T011 [P] Wire `dodoo/core/db.py` startup into `dodoo/__init__.py` `Environment` stub:
  define `Environment` class with `async classmethod create(database_url)` that creates the
  engine, calls `bootstrap()` (T014), and holds a reference; add `close()` async method;
  expose `env["model.name"]` dunder that raises `NotImplementedError` (will be wired in T027)
- [ ] T012 [P] Write `dodoo/__main__.py`: entry point for `python -m dodoo`; stub `server`
  and `module` subcommand parsers (implementations added in US2/US3 phases); parse
  `--host`, `--port`, `--database-url` for server subcommand
- [ ] T013 [P] File ADRs for all 9 research decisions in `docs/adr/`: one `.md` file per
  decision (ORM, async driver, module loader, migration strategy, password hashing, session
  storage, JSON-RPC dispatch, STI strategy, access rule enforcement); use format:
  title / status / context / decision / consequences
- [ ] T014 [P] Implement `dodoo/core/bootstrap.py`: `bootstrap(ddl_conn, dml_conn)` function
  that executes hard-coded `CREATE TABLE IF NOT EXISTS` SQL for the four core registry tables
  (`ir_module`, `ir_model`, `ir_model_field`, `ir_session`) using their canonical column
  definitions via `ddl_conn`; called from `Environment.create()` before any module install;
  this raw-SQL phase runs before the ORM is operational, solving the bootstrapping
  chicken-and-egg problem; wrap DDL in a transaction so partial failures roll back cleanly;
  after bootstrap, run `SELECT has_table_privilege(current_user, 'ir_module', 'TRIGGER')` on
  `dml_conn` — if the result is TRUE, emit `logging.warning("SEC-005: DATABASE_URL user
  holds DDL-level privileges; use a least-privilege credential in production")`
- [ ] T015 [P] Implement Python model classes for core registry tables in
  `dodoo/addons/base/models/ir_meta.py`: `IrModule` (`_name = "ir.module"`, fields: name
  Char required, version Char, state Char default "uninstalled", installed_version Char,
  depends Text), `IrModel` (`_name = "ir.model"`, fields: name Char required unique,
  table_name Char required unique, module_id Many2one→IrModule, description Text),
  `IrModelField` (`_name = "ir.model.field"`, fields: model_id Many2one→IrModel required,
  name Char required, field_type Char required, string Char, required Boolean, readonly
  Boolean, default_val Text, relation Char, relation_field Char, relation_table Char);
  import all three in `dodoo/addons/base/models/__init__.py`

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 — Model Registry & ORM (Priority: P1) 🎯 MVP

**Goal**: Developer can declare a model with typed fields; core auto-creates/migrates the DB
table; CRUD + domain-filter queries work in-process; STI child models share parent table.

**Independent Test**: Run `pytest tests/unit/ tests/integration/test_orm_crud.py
tests/integration/test_migrations.py` with a live PostgreSQL; all pass.

**OWASP Pre-check** (SEC-006): Before committing any US1 implementation task, review the OWASP
Top 10 for the ORM/registry subsystem and document findings in `docs/adr/`; key areas:
Injection (A03 — parameterised queries only, no string interpolation), Insecure Design
(A04 — reserved field name guards), Security Misconfiguration (A05 — column type enforcement).

### Tests for User Story 1 ⚠️ Write FIRST — must FAIL before implementation

- [ ] T016 [P] [US1] Write unit tests for all field types in `tests/unit/test_fields.py`:
  assert `Char(size=128)` has `col_type == VARCHAR(128)`; assert `Many2one('res.partner')`
  has `relation == 'res.partner'`; assert `required=True` propagates; test each of the
  9 field types from the spec; assert declaring a field named `id`, `create_date`, or
  `write_date` raises `DodooError` (reserved name guard)
- [ ] T017 [P] [US1] Write unit tests for model registry in `tests/unit/test_registry.py`:
  assert registering two models with same name raises `DodooError`; assert STI child model
  records parent name; assert `registry.lookup('res.partner')` returns correct class
- [ ] T018 [P] [US1] Write unit tests for domain filter compiler in `tests/unit/test_query.py`:
  assert each of the 10 operators compiles to correct SQLAlchemy expression; assert prefix
  `|` produces OR; assert empty domain `[]` produces no WHERE clause; assert unknown field
  raises `DomainError`

### Implementation for User Story 1

- [ ] T019 [US1] Implement `dodoo/core/fields.py`: `Field` base class with attrs
  (`name`, `string`, `required`, `readonly`, `default`); concrete subclasses `Char(size)`,
  `Integer`, `Boolean`, `Float`, `Date`, `Datetime`, `Text`; each exposes
  `to_sa_column() -> sqlalchemy.Column`
- [ ] T020 [US1] Implement relational fields in `dodoo/core/fields.py`: `Many2one(relation)`,
  `One2many(relation, relation_field)`, `Many2many(relation, relation_table)`; `Many2one`
  produces `Column(Integer, ForeignKey(...), ondelete='RESTRICT')`; `One2many`/`Many2many`
  produce no column (virtual)
- [ ] T021 [US1] Implement `dodoo/core/registry.py`: `ModelRegistry` class with `register(cls)`
  (raises on name collision), `lookup(name) -> type`, `all_models() -> list`; store STI
  inheritance chain: child records `_parent_model` name; registry is a singleton per
  `Environment` instance
- [ ] T022 [US1] Implement `BaseModel` metaclass in `dodoo/core/models.py`: collect `Field`
  class attrs into `_fields` dict; raise `DodooError` if any user field name matches a
  reserved system field (`id`, `create_date`, `write_date`, `_type`); auto-set `_name` from
  class attr or module path; call `registry.register(cls)` on class creation; add system
  fields `id` (Integer PK), `create_date` (Datetime), `write_date` (Datetime) to every model
- [ ] T023 [US1] Implement STI support in `dodoo/core/registry.py`: when a model declares
  `_inherit = 'parent.model'`, record the inheritance; `migration_runner` adds `_type`
  VARCHAR(128) column to parent table if not present; queries on child model inject
  `WHERE _type = 'child.model'`
- [ ] T024 [US1] Implement `dodoo/core/migration.py`: `MigrationRunner.install(model, conn)`:
  introspect `information_schema.columns` for the model's table using `DATABASE_MIGRATION_URL`
  connection; if table missing → CREATE TABLE with all field columns; if table exists → for
  each field not in pg_catalog add column via ALTER TABLE ADD COLUMN; raise
  `SchemaConflictError` if a type change or column removal is detected; wrap all DDL in a
  transaction
- [ ] T025 [US1] Implement `dodoo/core/query.py`: `compile_domain(model, domain) ->
  sqlalchemy.ClauseElement`; map operator strings to SA comparison methods; handle prefix
  `&` (default) and `|` using recursive descent; return `true()` for empty domain;
  validate field names against model's `_fields` dict
- [ ] T026 [US1] Implement CRUD methods on `BaseModel` in `dodoo/core/models.py`:
  `create(env, vals) -> int`, `read(env, ids, fields) -> list[dict]`,
  `write(env, ids, vals) -> bool`, `unlink(env, ids) -> bool`,
  `search(env, domain, limit, offset, order) -> list[int]`,
  `search_read(env, domain, fields, limit, offset, order) -> list[dict]`,
  `fields_get(env, attributes) -> dict`; all use SQLAlchemy Core parameterised queries
- [ ] T027 [US1] Wire `Environment.__getitem__` in `dodoo/__init__.py`: `env["model.name"]`
  returns a model proxy bound to the env's DB connection; proxy delegates CRUD calls to
  `BaseModel` static methods passing `env` as first arg
- [ ] T028 [US1] Write integration tests for CRUD + STI in `tests/integration/test_orm_crud.py`:
  define `TestContact` model inline; assert create/read/write/unlink round-trips; assert
  domain filter `[("name", "ilike", "acme")]` returns only matching rows; assert `Many2one`
  FK rejects invalid parent ID; assert STI child sees parent + child fields, parent query
  returns all rows
- [ ] T029 [US1] Write integration tests for migration runner in
  `tests/integration/test_migrations.py`: assert CREATE TABLE on first install; add a field
  to model, re-run, assert column added and existing rows retained; assert
  `SchemaConflictError` raised when field type changed

**Checkpoint**: User Story 1 independently functional. Library import + ORM works without
HTTP server. Run `python -c "import dodoo"` smoke test (imports only).

---

## Phase 4: User Story 2 — Module Loader (Priority: P2)

**Goal**: Add-on packages placed in `ADDONS_PATH` are discovered, dependency-ordered, and
installed with schema applied; upgrade adds columns without data loss; bad manifests and
circular deps fail with clear errors.

**Independent Test**: Run `pytest tests/unit/test_loader.py
tests/integration/test_migrations.py -k "loader or module"` — all pass without US3/US4.

**OWASP Pre-check** (SEC-006): Before committing any US2 implementation task, review the OWASP
Top 10 for the module loader and document findings in `docs/adr/`; key areas: Insecure Design
(A04 — manifest schema validation), Security Misconfiguration (A05 — ADDONS_PATH traversal
guard), Vulnerable and Outdated Components (A06 — manifest `depends` allowlist).

### Tests for User Story 2 ⚠️ Write FIRST — must FAIL before implementation

- [ ] T030 [P] [US2] Write unit tests for manifest parsing and discovery in
  `tests/unit/test_loader.py`: assert valid manifest passes; assert missing `depends` key
  raises `ModuleLoadError`; assert topological sort of A→B→C produces [A, B, C]; assert
  cycle A→B→A raises `CycleError`; assert missing dependency raises `ModuleLoadError`;
  assert empty or non-existent `ADDONS_PATH` returns empty discovery result with a WARNING
  log (no exception)

### Implementation for User Story 2

- [ ] T031 [US2] Implement `dodoo/modules/loader.py`: `AddonLoader` class;
  `discover(addons_path) -> dict[name, manifest]`: if `addons_path` does not exist or is
  empty log a WARNING and return `{}`; otherwise scan directory for packages containing
  `__manifest__.py`, import the manifest dict, validate required keys (`name`, `version`,
  `depends`), raise `ModuleLoadError` on missing/malformed manifest
- [ ] T032 [US2] Implement `AddonLoader.resolve_order(names) -> list[str]` in
  `dodoo/modules/loader.py`: build dependency graph from manifests; call
  `graphlib.TopologicalSorter`; catch `graphlib.CycleError` and re-raise as project
  `CycleError` with the cycle path in the message; raise `ModuleLoadError` for any
  dependency name not found in discovered packages
- [ ] T033 [US2] Implement `dodoo/modules/installer.py`: `ModuleInstaller.install(name, env)`:
  call `loader.resolve_order([name])`; for each module in resolved order: import package via
  `importlib.import_module(package_name)`; collect all `BaseModel` subclasses declared in
  the package; run `MigrationRunner.install(model, conn)` for each; update `ir_module` state
  to `installed` using the `IrModule` model (from T015)
- [ ] T034 [US2] Implement `ModuleInstaller.upgrade(name, env)` in
  `dodoo/modules/installer.py`: same as install but model migration diff is against existing
  columns; additive changes applied; `SchemaConflictError` raised and install halted on
  destructive change; state transitions `installed → to_upgrade → installed`
- [ ] T035 [US2] Create `dodoo/addons/base/__manifest__.py`:
  `{"name": "base", "version": "1.0.0", "depends": []}`; update
  `dodoo/addons/base/models/__init__.py` to import `IrModule`, `IrModel`, `IrModelField`
  from `ir_meta.py` (T015) alongside stub imports for US4 models
- [ ] T036 [US2] Wire `python -m dodoo module install <name>` in `dodoo/__main__.py`:
  parse subcommand; call `ModuleInstaller.install(name, env)`; log installed module name and
  version on success; exit non-zero with clear message on `ModuleLoadError` / `CycleError`
- [ ] T037 [US2] Write integration tests for module loader in
  `tests/integration/test_migrations.py` (module section): create two test add-on packages
  at temp path; B depends A; install B; assert A loads before B (log order); assert tables
  for both modules exist; add a field to A, re-install A, assert column added, existing rows
  intact; install module with missing dep, assert `ModuleLoadError` before any schema change

**Checkpoint**: User Stories 1 + 2 independently functional. `python -m dodoo module install
base` completes without error.

---

## Phase 5: User Story 3 — HTTP Layer (Priority: P3)

**Goal**: JSON-RPC 2.0 requests dispatched correctly; conformant error envelopes for all
failure modes; REST route registry accepts module-registered routes; auth middleware
validates session token before handler is invoked (stub until US4 wires real sessions).

**Independent Test**: Run `pytest tests/integration/test_http_jsonrpc.py` — all pass
(uses httpx AsyncClient; PostgreSQL via testcontainers).

**OWASP Pre-check** (SEC-006): Before committing any US3 implementation task, review the OWASP
Top 10 for the HTTP layer and document findings in `docs/adr/`; key areas: Broken Access
Control (A01 — auth middleware coverage), Injection (A03 — JSON-RPC param validation),
Security Misconfiguration (A05 — CORS restricted to localhost).

### Tests for User Story 3 ⚠️ Write FIRST — must FAIL before implementation

- [ ] T038 [P] [US3] Write integration tests for JSON-RPC 2.0 in
  `tests/integration/test_http_jsonrpc.py`: assert well-formed request to `common.version`
  returns `{"jsonrpc":"2.0","id":N,"result":{...}}`; assert missing `method` field returns
  error code `-32600`; assert unknown service returns `-32601`; assert wrong param count
  returns `-32602`; assert internal exception returns `-32603`; assert unauthenticated
  `object.execute_kw` returns `-32000` AuthenticationError; assert a
  conftest-fixture-registered route `GET /test/ping` (auth="public", registered via
  `RouteRegistry` in the test session's `conftest.py` setup and deregistered on teardown —
  do NOT register this route in any production module) returns 200

### Implementation for User Story 3

- [ ] T039 [US3] Implement `dodoo/http/middleware.py` — correlation ID + session validator
  stub: (1) generate `correlation_id` UUID for every request, inject into request state +
  structured log context; (2) define `session_validator` as a module-level callable variable
  `(token: str, env) -> int` that initially always raises `AuthenticationError` (stub); for
  routes with `auth="session"` call `session_validator(token, env)`, inject
  `request.state.uid` on success, return `-32000` JSON-RPC error or 401 HTTP response on
  failure; real implementation wired in T057 (US4)
- [ ] T040 [US3] Implement `dodoo/http/routing.py`: `RouteRegistry` singleton; `@http.route(
  path, methods, auth)` decorator registers handler; raises `RouteConflictError` if same
  (method, path) registered twice; `register_with_app(app: FastAPI)` iterates registry and
  calls `app.add_api_route()`; core routes (`/web/session/*`, `/web/health`) are protected
  from override
- [ ] T041 [US3] Implement `dodoo/http/jsonrpc.py`: `POST /jsonrpc` FastAPI handler;
  parse raw body, validate JSON-RPC 2.0 envelope (jsonrpc, method, id, params); dispatch
  `params.service + params.method` to internal dispatch table; return conformant success or
  error envelope; map Python exceptions → error codes: `AuthenticationError → -32000`,
  `AccessError → -32000`, `DomainError → -32602`, unhandled → `-32603`
- [ ] T042 [US3] Register `common` service methods in `dodoo/http/jsonrpc.py`:
  `common.authenticate(login, password)` → calls session manager (stub raising
  `AuthenticationError` until T057 wires real sessions), `common.logout()` → stub,
  `common.version()` → returns server version dict; register in dispatch table
- [ ] T043 [US3] Register `object` service in `dodoo/http/jsonrpc.py`:
  `object.execute_kw(model, method, args, kwargs)` → validates model exists in registry,
  validates method is public (not prefixed with `_`), calls `env[model].<method>(*args,
  **kwargs)`, returns serialised result; access rule enforcement applied by ORM layer
  (wired in US4)
- [ ] T044 [US3] Implement `dodoo/http/app.py`: `create_app(env) -> FastAPI`; add CORS
  middleware (localhost-only: origin `http://127.0.0.1:*`); add correlation ID + session
  middleware; mount JSON-RPC endpoint; call `RouteRegistry.register_with_app(app)`;
  add startup/shutdown hooks for DB engine lifecycle
- [ ] T045 [P] [US3] Register base module REST endpoints in
  `dodoo/addons/base/http/__init__.py`: `POST /web/session/authenticate` (calls
  `common.authenticate`), `POST /web/session/logout` (calls `common.logout`),
  `GET /web/health` (pings DB connection, returns `{"status":"ok","db":"connected"}` or
  503 `{"status":"degraded","db":"disconnected"}`)
- [ ] T046 [US3] Wire `python -m dodoo server --host --port` in `dodoo/__main__.py`:
  import uvicorn; call `create_app(env)`; run `uvicorn.run(app, host, port)` with JSON
  access logs enabled

**Checkpoint**: User Stories 1–3 functional. `python -m dodoo server` starts; health check
returns 200; `common.version` returns over JSON-RPC; all unauthenticated object calls return
`-32000` (stub middleware always rejects tokens until T057).

---

## Phase 6: User Story 4 — Auth & Access Control (Priority: P4)

**Goal**: Users authenticate with login/password; session created with Argon2id-verified
credentials; session token validates subsequent requests; ir.rule domain injection silently
restricts reads; write denial returns AccessError; logout immediately invalidates session;
middleware wired to real session validator.

**Independent Test**: Run `pytest tests/integration/test_access_rules.py` — all pass.

**OWASP Pre-check** (SEC-006): Before committing any US4 implementation task, review the OWASP
Top 10 for the auth/access subsystem and document findings in `docs/adr/`; key areas: Broken
Access Control (A01 — ir.rule completeness), Cryptographic Failures (A02 — Argon2id config),
Identification & Authentication Failures (A07 — session expiry and token entropy).

### Tests for User Story 4 ⚠️ Write FIRST — must FAIL before implementation

- [ ] T047 [P] [US4] Write integration tests for session lifecycle in
  `tests/integration/test_access_rules.py`: assert `authenticate("admin","admin")` returns
  token; assert token validates on next call; assert expired token (manipulate expire_date in
  DB) returns `AuthenticationError`; assert `logout()` invalidates token immediately;
  assert re-using invalidated token returns `AuthenticationError`
- [ ] T048 [P] [US4] Write integration tests for ir.rule enforcement in
  `tests/integration/test_access_rules.py`: create user A in group G1; create ir.rule
  restricting `test.model` to G1 on read; assert user NOT in G1 gets empty search results;
  assert user IN G1 sees all records; create write-deny rule; assert user in denied group
  raises `AccessError` on write

### Implementation for User Story 4

- [ ] T049 [US4] Implement `dodoo/addons/base/models/res_groups.py`: `res.groups` model with
  `Char` fields `name` (required), `full_name`, `category`; register with base module
- [ ] T050 [US4] Implement `dodoo/addons/base/models/res_users.py`: `res.users` model with
  `login` (Char, required, unique), `password_hash` (Char, readonly via ORM), `name` (Char,
  required), `active` (Boolean, default True), `group_ids` (Many2many → `res.groups`);
  add `_check_password(plain) -> bool` using `argon2.PasswordHasher().verify()`; add
  `_set_password(plain)` that hashes via `argon2.PasswordHasher().hash()` and stores in
  `password_hash`; NEVER log or return `password_hash` in `read()` — exclude it from
  default field list
- [ ] T051 [US4] Implement `dodoo/addons/base/models/ir_session.py`: `ir.session` model with
  `token` (Char 64, required, unique), `user_id` (Many2one → `res.users`, required),
  `create_date` (Datetime, default now), `expire_date` (Datetime, required)
- [ ] T052 [US4] Implement `dodoo/addons/base/models/ir_rule.py`: `ir.rule` model with
  `name` (Char, required), `model_id` (Many2one → `ir.model`, required), `domain_filter`
  (Text, required; validated as JSON list-of-tuples on write), `perm_read`, `perm_write`,
  `perm_create`, `perm_unlink` (Boolean, default True), `global_rule` (Boolean, default
  False), `group_ids` (Many2many → `res.groups`)
- [ ] T053 [US4] Implement `dodoo/auth/session.py`: `SessionManager.authenticate(env, login,
  password) -> str`: lookup user by login; verify Argon2id hash; raise `AuthenticationError`
  if inactive user or wrong password (same error — no user enumeration); generate token via
  `secrets.token_urlsafe(32)`; insert `ir.session` row with `expire_date = now +
  SESSION_EXPIRY_HOURS`; return token. `validate(env, token) -> int (uid)`: lookup token in
  `ir.session`; raise `AuthenticationError` if not found or `expire_date < now`.
  `invalidate(env, token)`: delete `ir.session` row for token
- [ ] T054 [US4] Implement `dodoo/auth/access.py`: `AccessEnforcer.get_applicable_rules(env,
  model_name, uid, operation) -> list[domain]`: load user's group IDs; query `ir.rule` for
  rules matching model, operation, and (global_rule=True OR group in user's groups); return
  list of domain filters. `merge_domain(base_domain, rules) -> domain`: AND-merge all rule
  domains into base domain. Raise `AccessError` for write/create/unlink if applicable rules
  deny the operation
- [ ] T055 [US4] Wire `AccessEnforcer` into `BaseModel` CRUD in `dodoo/core/models.py`:
  before `search()` / `read()` → call `get_applicable_rules` for read, merge domains into
  query WHERE; before `write()` / `create()` / `unlink()` → call enforcer; raise
  `AccessError` if denied; pass `uid=None` (bypass) when called from within module install
  (no active session)
- [ ] T056 [US4] Seed base data in `dodoo/addons/base/data/base_data.py`: create
  `Administrator` group; create `admin` user with hashed password `"admin"` (Argon2id);
  assign admin to Administrator group; seed called at end of `base` module install only if
  `res.users` table is empty (idempotent)
- [ ] T057 [US4] Wire real `SessionManager.validate()` into middleware `session_validator` in
  `dodoo/http/middleware.py`: replace the always-raising stub (T039) with a call to
  `SessionManager.validate(env, token)` from `dodoo/auth/session.py`; wire
  `common.authenticate` and `common.logout` in `dodoo/http/jsonrpc.py` (T042) to call
  the real `SessionManager` methods; add integration test assertion to
  `tests/integration/test_access_rules.py` that a valid token obtained via
  `common.authenticate` is accepted by a protected `object.execute_kw` call

**Checkpoint**: All 4 user stories functional. Full end-to-end: install base, authenticate,
CRUD via JSON-RPC, verify access control, logout.

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: CI gates, benchmarks, security audit, observability verification, documentation.

- [ ] T058 [P] Write e2e test in `tests/e2e/test_full_flow.py`: two scenarios — (1) library
  mode: spin up `Environment` without HTTP server, install `base`, perform `search()`, assert
  results (covers SC-005 / FR-015 automated); (2) HTTP mode: spin up server with testcontainer
  PostgreSQL, install `base`, authenticate as admin, create a `res.groups` record via
  JSON-RPC, search it back, logout, verify invalidated token returns `AuthenticationError`
- [ ] T059 [P] Write benchmark tests in `tests/benchmarks/test_performance.py`: insert 100k
  rows into a test model; measure p95 single-record lookup by ID (assert < 10ms, PERF-001);
  run 100 concurrent JSON-RPC requests; measure throughput (assert ≥ 200 req/s, PERF-002);
  generate 10 synthetic add-on packages with 5 models each and time
  `ModuleInstaller.install()` end-to-end (assert < 5s, PERF-003); add benchmark job to CI
  with 10% regression gate vs stored baseline
- [ ] T060 Security audit: review each subsystem against OWASP Top 10 checklist (document
  findings in `docs/adr/010-security-review.md`); grep codebase for string interpolation
  into SQL (assert none); grep for `password` in log calls (assert none); verify
  `password_hash` excluded from `read()` default fields; verify session token entropy ≥ 128
  bits; document alerting strategy in `docs/observability.md`: ERROR log entries + `/health`
  503 are the two alert surfaces; CI benchmark gate is the latency breach detector
- [ ] T061 [P] Observability validation: verify every HTTP request produces a structured log
  line with `correlation_id`; verify `GET /web/health` correctly returns 503 when DB
  unreachable (use testcontainers pause); verify `AuthenticationError` and `AccessError`
  log at WARN level (not DEBUG) without exposing token or password
- [ ] T062 [P] Verify `quickstart.md` scenarios 1–7 all produce expected output on a clean
  install; update any paths or commands that diverged during implementation
- [ ] T063 Run full CI gate sequence and confirm all pass with exit code 0: `ruff check .`,
  `ruff format --check .`, `pytest tests/unit/ --cov=dodoo --cov-report=term-missing`,
  `pytest tests/integration/`, `pytest tests/e2e/`, `pip-audit --strict`; document gate
  results in `docs/adr/011-ci-gates-validated.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 complete — BLOCKS all user stories
- **US1 ORM (Phase 3)**: Depends on Phase 2 — no dependency on US2/US3/US4
- **US2 Module Loader (Phase 4)**: Depends on Phase 2 + US1 (uses ModelRegistry,
  MigrationRunner, and IrModule model from T015)
- **US3 HTTP Layer (Phase 5)**: Depends on Phase 2 + US1 (uses Environment, BaseModel);
  `common.authenticate` and session middleware are stubs until T057 (US4)
- **US4 Auth/Access (Phase 6)**: Depends on US1 (ORM), US2 (base module install), US3
  (middleware interface defined in T039); T057 wires the real session validator
- **Polish (Phase N)**: Depends on all 4 user stories complete

### User Story Dependencies

- **US1 (P1)**: Only depends on Foundational phase ← START HERE
- **US2 (P2)**: Depends on US1 (uses ModelRegistry + MigrationRunner + IrModule T015)
- **US3 (P3)**: Depends on US1; can start concurrently with US2 (stub middleware is
  independent of US2); `object.execute_kw` needs US1 complete
- **US4 (P4)**: Depends on US1 + US2 (base module must be installable) + US3 (T039
  defines `session_validator` interface that T057 replaces)

### Within Each User Story

1. Write tests first (they MUST fail before implementation)
2. Implement fields / models before services
3. Implement services before endpoints
4. Complete story before moving to next priority

### Parallel Opportunities

All tasks marked `[P]` within a phase can run simultaneously:
- T016, T017, T018 (US1 tests) all write different files — parallel
- T019, T020 (fields) can overlap with T021 (registry) — different files
- T030 (US2 test) can be written while T027/T028/T029 integration tests run
- T047, T048 (US4 tests) — both write to same file; write T047 then T048

---

## Parallel Example: User Story 1

```bash
# Tests — all parallel (different files):
Task T016: tests/unit/test_fields.py
Task T017: tests/unit/test_registry.py
Task T018: tests/unit/test_query.py

# Implementation — some parallel:
Task T019 + T020: dodoo/core/fields.py   (T019 first, T020 extends same file)
Task T021: dodoo/core/registry.py        (parallel with T019/T020)
Task T025: dodoo/core/query.py           (parallel with T021/T022)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (includes bootstrap T014 + meta-models T015)
3. Complete Phase 3: US1 (ORM + registry)
4. **STOP and VALIDATE**: `python -c "import dodoo"` imports cleanly;
   unit + integration tests for US1 all pass
5. Deploy/demo: in-process ORM works as a library

### Incremental Delivery

1. Setup + Foundational → Project scaffolding + bootstrap ready
2. US1 ORM → Library usable in-process (MVP!)
3. US2 Module Loader → Add-ons installable from file system
4. US3 HTTP Layer → JSON-RPC + REST callable from any HTTP client (auth stubbed)
5. US4 Auth + Access → Real sessions wired; production-safe multi-user system
6. Polish → CI gates green, all benchmarks pass, security audited

### Parallel Team Strategy

With two developers after Foundational phase:
- Dev A: US1 (ORM core — blocks everything, highest priority)
- Dev B: Write US2 unit tests (T030) and stub structure for loader
- Once US1 complete: Dev A → US3, Dev B → US2; they converge at US4

---

## Notes

- `[P]` = can run in parallel (no shared file dependencies)
- `[Story]` = maps to spec user story for traceability
- Tests MUST be written and FAIL before implementation in each story
- `password_hash` MUST NEVER appear in logs, API responses, or `read()` output
- `SchemaConflictError` on destructive migration MUST halt install before any change
- `--no-verify` git bypass is prohibited (Principle VIII)
- `pip-audit` CI integration is owned by T004; T010 owns dev dep declaration only
- T039 middleware `session_validator` is a stub; T057 replaces it with the real validator
- Commit after each task or logical group
- Run `ruff check . && ruff format .` before every commit
