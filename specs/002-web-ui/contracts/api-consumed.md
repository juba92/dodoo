# API Contracts Consumed by the Web UI

The web UI is a pure consumer — it calls existing dodoo endpoints. No new server endpoints are introduced except the static file mount and the client entry point.

---

## Endpoint: POST /web/session/authenticate

**Called when**: User submits the login form.

**Request body**:
```json
{ "login": "admin", "password": "admin" }
```

**Success response** `200`:
```json
{ "uid": 1, "session_token": "<token>" }
```

**Failure response** `401`:
```json
{ "error": "Authentication failed" }
```

**Client behaviour**: Store `session_token` in `sessionStorage`; navigate to `#/home`. On 401: show inline error, stay on login page.

---

## Endpoint: POST /web/session/logout

**Called when**: User clicks Logout.

**Request headers**: `X-Session-Token: <token>`

**Request body**: `{}`

**Success response** `200`:
```json
{ "result": "ok" }
```

**Client behaviour**: Clear `sessionStorage`; navigate to `#/login`.

---

## Endpoint: GET /web/core/info

**Called when**: Home screen loads; also on app startup to populate model list.

**Success response** `200`:
```json
{
  "modules": [
    { "name": "base", "version": "1.0.0", "state": "installed" }
  ],
  "models": ["ir.model", "ir.module", "res.groups", "res.users"],
  "users": 1,
  "groups": 1
}
```

**Client behaviour**: Render module tiles; build sidebar model list.

---

## Endpoint: POST /jsonrpc — fields_get

**Called when**: A model's list or form view loads for the first time (cached after first call).

**Request body**:
```json
{
  "jsonrpc": "2.0", "method": "call", "id": 1,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": ["res.users", "fields_get", []],
    "kwargs": { "attributes": ["string", "type", "required", "readonly", "relation"] }
  }
}
```

**Success response**:
```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "login": { "string": "Login", "type": "char", "required": true, "readonly": false },
    "name":  { "string": "Name",  "type": "char", "required": true, "readonly": false }
  }
}
```

**Request headers**: `X-Session-Token: <token>`

---

## Endpoint: POST /jsonrpc — search_read

**Called when**: List view loads or search term changes.

**Request body**:
```json
{
  "jsonrpc": "2.0", "method": "call", "id": 2,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": ["res.users", "search_read", [[]]],
    "kwargs": { "fields": ["login", "name"], "limit": 50, "offset": 0 }
  }
}
```

**Success response**:
```json
{
  "jsonrpc": "2.0", "id": 2,
  "result": [
    { "id": 1, "login": "admin", "name": "Administrator" }
  ]
}
```

---

## Endpoint: POST /jsonrpc — read (single record)

**Called when**: Form view loads for an existing record.

**Request body**:
```json
{
  "jsonrpc": "2.0", "method": "call", "id": 3,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": ["res.users", "read", [[1]]],
    "kwargs": { "fields": ["login", "name", "active"] }
  }
}
```

**Success response**:
```json
{
  "jsonrpc": "2.0", "id": 3,
  "result": [{ "id": 1, "login": "admin", "name": "Administrator", "active": true }]
}
```

---

## Endpoint: POST /jsonrpc — write (update)

**Called when**: User clicks Save on an existing record.

**Request body**:
```json
{
  "jsonrpc": "2.0", "method": "call", "id": 4,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": ["res.users", "write", [[1], { "name": "Admin Updated" }]],
    "kwargs": {}
  }
}
```

**Success response**: `{ "result": true }`

---

## Endpoint: POST /jsonrpc — create

**Called when**: User clicks Save on a new (unsaved) record.

**Request body**:
```json
{
  "jsonrpc": "2.0", "method": "call", "id": 5,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": ["res.users", "create", [{ "login": "bob", "name": "Bob", "password_hash": "" }]],
    "kwargs": {}
  }
}
```

**Success response**: `{ "result": 2 }` (new record ID)

---

## Endpoint: POST /jsonrpc — unlink (delete)

**Called when**: User confirms the Delete dialog.

**Request body**:
```json
{
  "jsonrpc": "2.0", "method": "call", "id": 6,
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": ["res.users", "unlink", [[2]]],
    "kwargs": {}
  }
}
```

**Success response**: `{ "result": true }`

---

## New Endpoints Added by this Addon

| Method | Path | Description |
|---|---|---|
| GET | `/web/client` | Returns `index.html` — the SPA entry point |
| `*` | `/web/static/*` | Static file mount (JS, CSS) |
