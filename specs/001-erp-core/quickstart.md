# Quickstart Validation Guide: Minimal ERP Core

**Feature**: `001-erp-core` | **Date**: 2026-06-06

This guide describes how to validate that the ERP core is working end-to-end after
implementation. It is a **validation/run guide**, not implementation instructions.

---

## Prerequisites

- Python 3.12 installed
- PostgreSQL 15 running locally (default port 5432)
- A database created: `createdb dodoo_dev`
- Environment variables set (see `.env.example`):
  ```
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dodoo_dev
  SESSION_EXPIRY_HOURS=8
  ADDONS_PATH=./addons
  ```
- Dependencies installed: `pip install -e ".[dev]"`

---

## Scenario 1: Library Import (no HTTP server)

Validates that the system is usable as a Python library (Success Criterion SC-005).

```bash
python - <<'EOF'
import asyncio
from dodoo import Environment

async def main():
    env = await Environment.create()          # connects to DB
    await env.modules.install("base")         # installs base module + schema
    users = await env["res.users"].search([]) # should return admin user
    print("Users found:", len(users))
    await env.close()

asyncio.run(main())
EOF
```

**Expected output**: `Users found: 1` (the default admin user seeded by `base`)

---

## Scenario 2: Start the HTTP Server

```bash
python -m dodoo server --host 127.0.0.1 --port 8069
```

**Expected**: Server starts, logs `INFO dodoo.http started on 127.0.0.1:8069`, no errors.

Health check:
```bash
curl -s http://127.0.0.1:8069/web/health | python -m json.tool
```
**Expected**:
```json
{"status": "ok", "db": "connected"}
```

---

## Scenario 3: Authenticate via JSON-RPC

Validates SC-002 (authentication scenarios).

```bash
curl -s -X POST http://127.0.0.1:8069/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "method": "call", "id": 1,
    "params": {
      "service": "common", "method": "authenticate",
      "args": ["admin", "admin"], "kwargs": {}
    }
  }' | python -m json.tool
```

**Expected**: `result.session_token` is a non-empty string; `result.uid` is an integer.

Store the token: `TOKEN=<value from result.session_token>`

**Test expired/invalid token**:
```bash
curl -s -X POST http://127.0.0.1:8069/jsonrpc \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: invalid_token_xyz" \
  -d '{"jsonrpc":"2.0","method":"call","id":2,"params":{"service":"object","method":"execute_kw","args":["res.users","search",[[]]],"kwargs":{}}}' \
  | python -m json.tool
```
**Expected**: `error.code` is `-32000`, `error.data.type` is `"AuthenticationError"`.

---

## Scenario 4: CRUD via JSON-RPC

Validates SC-001 (full CRUD without modifying core files).

```bash
# Create a group
curl -s -X POST http://127.0.0.1:8069/jsonrpc \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: $TOKEN" \
  -d '{
    "jsonrpc":"2.0","method":"call","id":3,
    "params":{"service":"object","method":"execute_kw",
      "args":["res.groups","create",[{"name":"Sales","full_name":"Sales / User"}]],
      "kwargs":{}}
  }' | python -m json.tool
```
**Expected**: `result` is an integer (new group ID).

```bash
# Read it back
curl -s -X POST http://127.0.0.1:8069/jsonrpc \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: $TOKEN" \
  -d "{
    \"jsonrpc\":\"2.0\",\"method\":\"call\",\"id\":4,
    \"params\":{\"service\":\"object\",\"method\":\"execute_kw\",
      \"args\":[\"res.groups\",\"search_read\",[[\"name\",\"=\",\"Sales\"]],{\"fields\":[\"name\",\"full_name\"]}],
      \"kwargs\":{}}
  }" | python -m json.tool
```
**Expected**: Array with one object: `{"id": N, "name": "Sales", "full_name": "Sales / User"}`.

---

## Scenario 5: Install a Custom Add-on

Validates SC-001 and SC-003 (module loader, no core modification).

1. Create a minimal add-on at `./addons/my_partner/__manifest__.py`:
   ```python
   {"name": "My Partner", "version": "1.0", "depends": ["base"]}
   ```
2. Create `./addons/my_partner/models/partner.py` with a `my.partner` model declaration
   (refer to implementation docs for model class API).
3. Install:
   ```bash
   python -m dodoo module install my_partner
   ```
   **Expected**: Logs show `base` loaded first, then `my_partner`; table `my_partner` exists
   in the database.

4. Verify table exists:
   ```bash
   psql $DATABASE_URL -c "\d my_partner"
   ```

---

## Scenario 6: Access Rule Enforcement

Validates SC-004 (row-level security).

Run the integration test directly (no manual HTTP needed):
```bash
pytest tests/integration/test_access_rules.py -v
```

**Expected**: All tests pass, including:
- `test_user_without_group_sees_zero_results`
- `test_user_with_group_sees_restricted_records`
- `test_write_denied_returns_access_error`

---

## Scenario 7: CI Gate Validation

Validates SC-006.

```bash
# Full CI sequence (must all pass, no bypass flags)
ruff check .                          # linting
ruff format --check .                 # formatting
pytest tests/unit/ --cov=dodoo --cov-report=term-missing  # unit + coverage
pytest tests/integration/             # integration (requires running PostgreSQL)
pytest tests/e2e/                     # end-to-end
```

**Expected**: All exit code 0. Coverage report shows ≥ 80% line coverage for `dodoo/`.

---

## Troubleshooting

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| `asyncpg.InvalidCatalogNameError` | Database does not exist | `createdb dodoo_dev` |
| `ModuleNotFoundError: dodoo` | Package not installed | `pip install -e .` |
| `CycleError` on module install | Circular dependency in add-on | Review `__manifest__.py` `depends` |
| `SchemaConflictError` on upgrade | Destructive column change attempted | Defer or remove the field change |
| `-32000 AuthenticationError` | Token expired | Re-authenticate via `common.authenticate` |
