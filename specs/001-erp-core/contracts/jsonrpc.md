# Contract: JSON-RPC 2.0 Endpoint

**Feature**: `001-erp-core` | **Date**: 2026-06-06

## Endpoint

```
POST /jsonrpc
Content-Type: application/json
X-Session-Token: <token>   (required for object service; omit for common/authenticate)
```

---

## Request Envelope (JSON-RPC 2.0)

```json
{
  "jsonrpc": "2.0",
  "method": "call",
  "id": <integer | string | null>,
  "params": {
    "service": "<service_name>",
    "method": "<method_name>",
    "args": [<positional args>],
    "kwargs": {<keyword args>}
  }
}
```

- `jsonrpc`: MUST be `"2.0"`
- `method`: MUST be `"call"` (the only top-level method; service dispatch is via `params.service`)
- `id`: Any JSON scalar; `null` for notifications (no response expected)
- `params.service`: One of `common`, `object`
- `params.args` / `params.kwargs`: Optional; default to `[]` / `{}`

---

## Success Response Envelope

```json
{
  "jsonrpc": "2.0",
  "id": <same id as request>,
  "result": <any JSON value>
}
```

---

## Error Response Envelope

```json
{
  "jsonrpc": "2.0",
  "id": <same id as request | null>,
  "error": {
    "code": <integer>,
    "message": "<short description>",
    "data": {
      "type": "<error_type>",
      "debug": "<optional stack trace or detail, omitted in production>"
    }
  }
}
```

### Standard Error Codes

| Code | Meaning | When |
|------|---------|------|
| -32700 | Parse error | Request body is not valid JSON |
| -32600 | Invalid request | Missing `jsonrpc`, `method`, or `params` |
| -32601 | Method not found | `service` or `method` not registered |
| -32602 | Invalid params | Wrong number or type of arguments |
| -32603 | Internal error | Unhandled server exception |
| -32000 | Application error | Auth failure, access denied, validation error |

---

## Services

### Service: `common`

Authentication and server identity. Does not require a session token.

#### `common.authenticate`

Verify credentials and create a session.

**Args**: `[login: str, password: str]`

**Returns on success**:
```json
{
  "uid": 3,
  "session_token": "abc123..."
}
```

**Returns on failure** (wrong credentials or inactive user):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32000,
    "message": "Authentication failed",
    "data": { "type": "AuthenticationError" }
  }
}
```

---

#### `common.logout`

Invalidate an active session.

**Header**: `X-Session-Token: <token>`
**Args**: `[]`
**Returns**: `true`

---

#### `common.version`

Return server version information (no auth required).

**Args**: `[]`
**Returns**:
```json
{
  "server_version": "0.1.0",
  "protocol_version": "1"
}
```

---

### Service: `object`

Model CRUD and method dispatch. **Requires** a valid `X-Session-Token` header on every call.
An expired or missing token returns error code `-32000` with type `AuthenticationError`.

#### `object.execute_kw`

Execute a model method.

**Args**: `[model: str, method: str, args: list, kwargs: dict]`

- `model`: Registered model name (e.g., `"res.partner"`)
- `method`: Method name on the model class (e.g., `"search"`, `"read"`, `"create"`, `"write"`, `"unlink"`)
- `args`: Positional arguments
- `kwargs`: Keyword arguments

**Standard model methods**:

| Method | Signature | Returns |
|--------|-----------|---------|
| `search` | `(domain, limit, offset, order)` | `[id, ...]` |
| `read` | `(ids, fields)` | `[{field: val, ...}, ...]` |
| `search_read` | `(domain, fields, limit, offset, order)` | `[{field: val, ...}, ...]` |
| `create` | `(vals: dict)` | `new_id: int` |
| `write` | `(ids: list[int], vals: dict)` | `true` |
| `unlink` | `(ids: list[int])` | `true` |
| `fields_get` | `(attributes: list[str])` | `{field_name: {attr: val}}` |

**Example — search_read**:
```json
{
  "jsonrpc": "2.0",
  "method": "call",
  "id": 42,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": [
      "res.partner",
      "search_read",
      [[["active", "=", true]]],
      {"fields": ["name", "email"], "limit": 10}
    ]
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": [
    {"id": 1, "name": "ACME Corp", "email": "info@acme.example"},
    {"id": 2, "name": "Globex", "email": null}
  ]
}
```

---

## Domain Filter Syntax

A domain is a JSON array of 3-element tuples: `[[field, operator, value], ...]`

Supported operators:

| Operator | Meaning |
|----------|---------|
| `=` | Equal |
| `!=` | Not equal |
| `<` | Less than |
| `>` | Greater than |
| `<=` | Less than or equal |
| `>=` | Greater than or equal |
| `in` | Value in list |
| `not in` | Value not in list |
| `like` | Case-sensitive pattern (SQL LIKE) |
| `ilike` | Case-insensitive pattern (SQL ILIKE) |

Logical operators `&` (AND, default) and `|` (OR) may be prepended as prefix operators following
Polish notation (same convention as Odoo):
```json
["|", ["state", "=", "open"], ["state", "=", "draft"]]
```

An empty domain `[]` matches all records (subject to ir.rule filtering).

---

## Access Rule Behaviour

All `object` service calls are subject to `ir.rule` enforcement:

- **Read operations** (`search`, `read`, `search_read`): restricted domains are AND-merged into
  the query's WHERE clause; restricted records are not returned (silent, not an error).
- **Write / create / unlink operations**: if the record does not pass the applicable rule domain,
  the operation returns error code `-32000` with type `AccessError`.

---

## Session Token Transmission

- Token is transmitted in the `X-Session-Token` HTTP header (not in the request body or URL).
- Token format: URL-safe base64, 43 characters (32 bytes = 256 bits entropy).
- Expired tokens return `-32000` `AuthenticationError`; the client MUST re-authenticate.
