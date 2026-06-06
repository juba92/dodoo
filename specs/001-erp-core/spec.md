# Feature Specification: Minimal ERP Core

**Feature Branch**: `001-erp-core`

**Created**: 2026-06-06

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Define and Persist Domain Models (Priority: P1)

A module developer declares a domain model (e.g., a "Partner" record with name, email, and a
link to a company) using declarative field definitions. The core registers this model, creates or
migrates the backing database table, and exposes CRUD operations on it.

**Why this priority**: All other subsystems depend on the model registry being able to store and
retrieve typed records. Without it, no module can function.

**Independent Test**: Declare a two-field model; verify the table is created; insert a record;
retrieve it by ID; update a field; delete the record. No other subsystem needs to be running.

**Acceptance Scenarios**:

1. **Given** a model class with Char, Integer, and Many2one field declarations, **When** the
   registry processes the class, **Then** the backing table exists with correctly typed columns
   and foreign key constraints.

2. **Given** a registered model, **When** a CRUD create is called with valid data, **Then** the
   record is persisted and returned with a system-assigned integer ID.

3. **Given** a registered model with records, **When** a domain filter query is executed
   (e.g., `[("name", "=", "ACME")]`), **Then** only matching records are returned.

4. **Given** a parent model and a child model with a Many2one field, **When** the child record
   is created with a valid parent ID, **Then** referential integrity is enforced (invalid parent
   ID is rejected).

5. **Given** a model that extends another registered model (single-table inheritance), **When**
   both are queried, **Then** each sees only its own fields plus the parent's fields.

---

### User Story 2 — Load and Install Add-on Modules (Priority: P2)

A developer places an add-on package in the add-ons directory. When the server starts (or an
install command is issued), the loader discovers the package, validates its dependency manifest,
resolves the load order, and installs or upgrades the database schema for all declared models.

**Why this priority**: Without the module loader, every feature would need to be baked into
core. The loader is what makes the system extensible.

**Independent Test**: Place two packages — B depends on A — in the add-ons directory; invoke
the install routine; verify A initialises before B; verify both models' tables exist; re-run
with a new field added to A's model and verify the column is added without data loss.

**Acceptance Scenarios**:

1. **Given** an add-on directory containing packages with `__manifest__.py` files, **When** the
   loader scans the directory, **Then** it enumerates all packages and reads their dependency
   declarations.

2. **Given** packages with dependency declarations, **When** the loader resolves load order,
   **Then** packages are initialised in dependency-topological order; circular dependencies raise
   a clear error before any schema changes occur.

3. **Given** an already-installed module whose model gains a new optional field, **When** the
   upgrade routine runs, **Then** the column is added to the existing table and pre-existing rows
   retain their data.

4. **Given** a module that declares a dependency on a package not present in the add-ons
   directory, **When** the loader attempts to resolve dependencies, **Then** it raises a clear
   error naming the missing dependency before any schema changes occur.

---

### User Story 3 — Call Business Logic over HTTP (Priority: P3)

A client application calls the server's JSON-RPC 2.0 endpoint or a REST route to execute model
operations (read, write, search) and invoke custom methods registered by modules. The server
authenticates the session, enforces access rules, and returns a structured response.

**Why this priority**: Exposes the ORM and business logic over the network, making the core
useful to any HTTP client without requiring Python bindings.

**Independent Test**: Start the server with a test module loaded; send a valid JSON-RPC 2.0
request to create a record; verify the response contains the new record's ID; send the same
request without a valid session token and verify a structured authentication error is returned.

**Acceptance Scenarios**:

1. **Given** a running server, **When** a client sends a well-formed JSON-RPC 2.0 request to
   `/jsonrpc`, **Then** the server dispatches it to the correct model method and returns a
   conformant JSON-RPC 2.0 response envelope.

2. **Given** a module that registers a REST route, **When** a client sends an HTTP request to
   that route, **Then** the server dispatches to the registered handler and returns the handler's
   response with the correct HTTP status code.

3. **Given** a malformed JSON-RPC 2.0 request (missing `method` or invalid `params`), **When**
   the server receives it, **Then** it returns a JSON-RPC 2.0 error response (code `-32600` or
   `-32602`) — not an unhandled exception.

4. **Given** a request whose JSON-RPC method does not exist, **When** the server receives it,
   **Then** it returns error code `-32601` (Method not found).

---

### User Story 4 — Authenticate and Enforce Access Control (Priority: P4)

A user logs in with a username and password. The server creates a session, associates it with the
user's groups, and enforces row-level access rules on every subsequent request. Accessing a
resource the user's groups do not permit returns a clear authorisation error, not raw data.

**Why this priority**: A multi-user system with no access control is not safe to expose on any
network interface, even localhost. Auth is a prerequisite for all real usage.

**Independent Test**: Create two users in different groups; log in as each; verify user A cannot
read records restricted to user B's group via an ir.rule-equivalent filter; verify logout
invalidates the session immediately.

**Acceptance Scenarios**:

1. **Given** a registered user with a correct password, **When** a login request is issued,
   **Then** the server returns a session token and the session is persisted server-side with a
   defined expiry.

2. **Given** a valid session token, **When** it is included in a subsequent request, **Then** the
   request is processed as the authenticated user.

3. **Given** an expired or invalid session token, **When** it is included in a request, **Then**
   the server returns a structured authentication error without processing the request.

4. **Given** a user belonging to group G, and a record-level access rule restricting a model to
   group G, **When** a user not in group G queries that model, **Then** the query returns zero
   results (filter applied silently, not an error).

5. **Given** an access rule that denies write on a model for group G, **When** a user in group G
   attempts a write, **Then** the server returns a permission-denied error.

6. **Given** a logged-in user, **When** a logout request is issued, **Then** the session is
   invalidated immediately and the token cannot be reused.

---

### Edge Cases

- What happens when a module declares a field with the same name as a core reserved field
  (e.g., `id`, `create_date`)?
- How does the system handle a schema migration that would require a destructive column change
  (type change or removal) on a table with existing data?
- What happens if the add-ons directory is empty or does not exist at startup?
- How does the server respond if the database connection is lost mid-request?
- What happens when two modules declare models with the same registry name?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a declarative model definition API supporting at minimum:
  Char, Integer, Boolean, Float, Date, Datetime, Text, Many2one, One2many, Many2many field types.
- **FR-002**: The model registry MUST auto-create or migrate the backing database table when a
  model is registered or upgraded, without data loss on additive migrations.
- **FR-003**: The ORM MUST support domain-filter queries using a list-of-tuples syntax
  `(field, operator, value)` with operators: `=`, `!=`, `<`, `>`, `<=`, `>=`, `in`, `not in`,
  `like`, `ilike`.
- **FR-004**: The ORM MUST enforce referential integrity for Many2one fields at the database level.
- **FR-005**: The system MUST support single-table inheritance: a child model extends a parent
  model and shares its table, with child-specific fields in additional columns.
- **FR-006**: The module loader MUST discover add-on packages by scanning a configurable
  add-ons directory for packages containing a `__manifest__.py` with `name`, `version`, and
  `depends` keys.
- **FR-007**: The module loader MUST resolve package dependencies topologically and raise a
  clear error for missing dependencies or circular dependency chains before any schema change.
- **FR-008**: The module loader MUST support additive schema upgrades: new columns and tables
  are applied when a module is re-installed; destructive changes raise a clear error and halt.
- **FR-009**: The HTTP layer MUST expose a `/jsonrpc` endpoint handling JSON-RPC 2.0 requests,
  dispatching to registered model methods or service functions.
- **FR-010**: The HTTP layer MUST support lightweight REST route registration by modules,
  mapping HTTP method + path pattern to a handler function.
- **FR-011**: The HTTP layer MUST return conformant JSON-RPC 2.0 error envelopes for all error
  conditions (invalid request, method not found, internal error).
- **FR-012**: The system MUST support session-based authentication: login returns an opaque
  session token; subsequent requests include the token; sessions have a configurable expiry.
- **FR-013**: The system MUST include a `res.users` model and a `res.groups` model; users belong
  to one or more groups.
- **FR-014**: The system MUST support record-level access rules (ir.rule equivalent): rules
  associate a domain filter with a group and an operation (read/write/create/unlink); the ORM
  applies the domain filter transparently on all matching queries.
- **FR-015**: The system MUST be importable as a Python library; all core subsystems MUST be
  instantiable programmatically without starting the HTTP server.

### Key Entities

- **Model**: A declarative class registered with the model registry; maps to a database table;
  carries field definitions and business methods.
- **Field**: A typed attribute on a model (Char, Integer, Many2one, etc.); carries metadata
  (required, default, readonly, string label).
- **Module / Add-on**: A Python package with a `__manifest__.py`; declares dependencies and
  registers models, routes, and data.
- **Session**: An authenticated server-side context associated with a user; identified by an
  opaque token with a configurable expiry time.
- **User (res.users)**: A principal that can authenticate; has a login, hashed password, and
  membership in one or more groups.
- **Group (res.groups)**: A named set of permissions; users inherit the access rules bound to
  their groups.
- **Access Rule (ir.rule)**: A record-level domain filter bound to a group and an operation;
  applied by the ORM transparently on every matching query.

### Security Requirements *(mandatory for this feature)*

- **SEC-001**: All input at system boundaries (HTTP request body, JSON-RPC params, domain filter
  tuples, file paths in add-on discovery) MUST be validated before processing.
- **SEC-002**: Passwords MUST be stored using Argon2id (argon2-cffi library); bcrypt is
  explicitly excluded — see research.md decision #5. Plaintext passwords MUST never be
  logged or persisted anywhere.
- **SEC-003**: Session tokens MUST be cryptographically random with at least 128 bits of entropy;
  tokens MUST NOT be predictable or sequential.
- **SEC-004**: The ORM MUST use parameterised queries exclusively; string interpolation into SQL
  is prohibited.
- **SEC-005**: The principle of least privilege MUST govern database credentials; application
  credentials MUST NOT hold DDL privileges in production.
- **SEC-006**: OWASP Top 10 checklist review is required before implementation of each subsystem.

### Performance Requirements

- **PERF-001**: Single-record lookup by ID MUST complete in under 10ms (p95) on a local database
  with up to 100,000 records in the table.
- **PERF-002**: The HTTP layer MUST sustain at least 200 JSON-RPC requests per second on a
  single-process localhost deployment without request queuing exceeding 50ms.
- **PERF-003**: Module loading (discovery + dependency resolution + schema migration for 10
  modules with 5 models each) MUST complete in under 5 seconds on first install.
- **PERF-004**: No performance regressions exceeding 10% from baseline are permitted; benchmarks
  for critical ORM paths MUST run in CI.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can declare a new domain model with 5 fields, install it as an add-on,
  perform CRUD operations via the JSON-RPC endpoint, and observe the correct data in the
  database — all without modifying any core files.
- **SC-002**: All four authentication scenarios (valid login, valid session, expired token,
  logout) pass under automated test with no manual intervention.
- **SC-003**: A module B that depends on module A loads after A in 100% of test runs; reversing
  the declared dependency order produces a clear error, not a silent failure.
- **SC-004**: A user without the required group receives zero results (not an error) when
  querying a row-restricted model, and receives a permission error when attempting a
  write-restricted operation — verified by automated test.
- **SC-005**: The system is importable as a library: a script with no HTTP server running can
  instantiate the registry, load a module, and perform ORM operations in-process.
- **SC-006**: All CI gates (lint, format, unit coverage ≥ 80%, integration tests, security scan)
  pass on every pull request with no bypass flags.

## Assumptions

- Single-tenant, single-process, localhost deployment only; no multi-tenancy, clustering, or
  TLS concerns in this milestone.
- No user-facing UI (HTML, templates, assets) in this milestone; all interaction is via
  JSON-RPC or REST endpoints.
- PostgreSQL is the only supported database backend for this milestone.
- Add-on packages are trusted code installed by a developer; the system does not sandbox module
  execution.
- Sessions are stored server-side (in-process or in a dedicated table); Redis or external session
  stores are out of scope for this milestone.
- The `res.users` and `res.groups` models are part of a built-in `base` module shipped with
  core, not an external add-on.
- Destructive schema migrations (column removal, type change) are deferred to a future milestone;
  the upgrade routine raises a clear error when one is detected.
- The HTTP server runs as a single ASGI process; no worker process pool is required.
