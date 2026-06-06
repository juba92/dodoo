# Contract: REST Route Registry

**Feature**: `001-erp-core` | **Date**: 2026-06-06

The core HTTP layer provides a lightweight REST route registry that add-on modules use to
expose custom HTTP endpoints alongside the JSON-RPC endpoint. This document defines the
route registration contract that module developers depend on.

---

## Route Registration API

Modules register REST routes by calling the route decorator provided by the HTTP layer.
This is a design contract, not an implementation detail — it defines what a module developer
can rely on.

### Decorator signature

```
@http.route(path, methods, auth)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | `str` | Yes | URL path pattern; path parameters use `{param}` syntax (e.g., `/api/partners/{id}`) |
| `methods` | `list[str]` | Yes | HTTP methods accepted (e.g., `["GET", "POST"]`) |
| `auth` | `str` | Yes | Auth mode: `"session"` (requires valid session token) or `"public"` (no auth) |

### Handler signature

```
async def handler(request, **path_params) -> Response
```

- `request`: The HTTP request object (method, headers, body, query params)
- `path_params`: Named path parameters extracted from the URL pattern
- Return value: An HTTP response object with `status_code`, `content`, and `headers`

---

## Core-Provided REST Endpoints

The `base` module registers the following REST endpoints during installation:

### `POST /web/session/authenticate`

Alternative to JSON-RPC auth for REST clients that prefer a dedicated login endpoint.

**Request body** (JSON):
```json
{
  "login": "admin",
  "password": "secret"
}
```

**Response 200**:
```json
{
  "uid": 1,
  "session_token": "abc123..."
}
```

**Response 401**:
```json
{
  "error": "Authentication failed"
}
```

---

### `POST /web/session/logout`

**Header**: `X-Session-Token: <token>`
**Response 200**: `{"result": "ok"}`

---

### `GET /web/health`

Health check endpoint for monitoring. No auth required.

**Response 200**:
```json
{
  "status": "ok",
  "db": "connected"
}
```

**Response 503** (database unreachable):
```json
{
  "status": "degraded",
  "db": "disconnected"
}
```

---

## Response Format Conventions

All REST handlers registered through the route registry MUST follow these conventions:

| Scenario | HTTP Status | Body |
|----------|-------------|------|
| Success | 200 | JSON payload |
| Created | 201 | JSON payload with `id` of created resource |
| Bad request (validation) | 400 | `{"error": "<message>"}` |
| Unauthenticated | 401 | `{"error": "Authentication required"}` |
| Forbidden | 403 | `{"error": "Access denied"}` |
| Not found | 404 | `{"error": "Not found"}` |
| Internal error | 500 | `{"error": "Internal server error"}` (detail omitted in production) |

- All responses: `Content-Type: application/json`
- Error bodies MUST NOT include stack traces in production

---

## Auth Mode Behaviour

| `auth` value | Session token required | Behaviour if missing/expired |
|---|---|---|
| `"session"` | Yes (`X-Session-Token` header) | Returns 401 immediately; handler not called |
| `"public"` | No | Handler called; `request.user` is `None` |

---

## Route Priority and Conflict Resolution

- Routes are registered in module load order (determined by the module loader's topological sort)
- If two modules register the same `(method, path)` combination, the second registration raises
  a `RouteConflictError` at startup — not at request time
- Core routes registered by `base` have priority over add-on routes only in error handling;
  add-ons cannot override `/web/session/*` or `/web/health`
