# ADR-010: Security Review — OWASP Top 10 Audit

**Status**: Accepted | **Date**: 2026-06-06

## A01 — Broken Access Control
- ir.rule domain injection enforced before every search/write (ADR-009)
- Session token required for all `object` service calls
- Private methods (prefixed `_`) rejected at JSON-RPC dispatch layer

## A02 — Cryptographic Failures
- Argon2id (memory-hard) for password hashing — bcrypt excluded (ADR-005)
- Session tokens: `secrets.token_urlsafe(32)` = 256-bit entropy (>= 128-bit minimum)
- Passwords never logged or returned in read() output

## A03 — Injection
- All queries use SQLAlchemy Core parameterised statements — zero string interpolation into SQL
- Domain filter fields validated against model._fields before compilation

## A04 — Insecure Design
- Reserved field names (id, create_date, write_date, _type) blocked by metaclass
- Manifest files evaluated with ast.literal_eval (no exec/eval)
- User enumeration prevented: same AuthenticationError for wrong login and wrong password

## A05 — Security Misconfiguration
- CORS restricted to localhost origins only
- DATABASE_URL user warned if holding DDL privileges (SEC-005 check in bootstrap)
- Two separate DB connections: DDL (DATABASE_MIGRATION_URL) and DML (DATABASE_URL)

## A06 — Vulnerable and Outdated Components
- pip-audit runs in CI and blocks on HIGH/CRITICAL CVEs
- All dependencies pinned in pyproject.toml

## A07 — Identification and Authentication Failures
- Session expiry configurable via SESSION_EXPIRY_HOURS
- Expired tokens return AuthenticationError (same as invalid tokens — no timing side-channel)
- Logout immediately deletes session row

## A08 — Software and Data Integrity Failures
- Manifest parsing uses ast.literal_eval — no arbitrary code execution
- SchemaConflictError halts upgrade before any destructive change

## A09 — Security Logging and Monitoring Failures
- Structured JSON logging with correlation_id on every request
- AuthenticationError and AccessError logged at WARN level (no token/password in logs)
- /web/health 503 is the primary alert surface for DB outages

## A10 — Server-Side Request Forgery
- No outbound HTTP calls in this milestone — SSRF surface is N/A
