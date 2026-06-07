# Data Model: Dodoo Web UI

The web UI addon introduces **no new database tables**. It is a pure frontend that reads from and writes to existing dodoo models via the JSON-RPC API.

## Client-Side State Model

The following describes the in-memory state managed by the browser application.

---

### Session

Represents the authenticated user's session. Persisted in `sessionStorage`.

| Field | Type | Description |
|---|---|---|
| `token` | string | Session token returned by `/web/session/authenticate` |
| `uid` | integer | Authenticated user ID |

**Lifecycle**: Created on successful login. Cleared on logout or 401 response.

---

### Module (client view of `ir.module`)

Represents an installed addon as shown on the home screen.

| Field | Type | Description |
|---|---|---|
| `name` | string | Technical name (e.g., `base`) |
| `version` | string | Version string (e.g., `1.0.0`) |
| `state` | string | Always `installed` for displayed modules |
| `icon` | string | CSS class or emoji mapped from module name |
| `label` | string | Human-readable display name (title-cased from `name`) |

**Source**: `/web/core/info` → `modules[]`

---

### Model (client view of registered ORM models)

Represents a registered model available for browsing.

| Field | Type | Description |
|---|---|---|
| `name` | string | Technical model name (e.g., `res.users`) |
| `label` | string | Human-readable name derived from model name |
| `module` | string | Which module this model belongs to (inferred) |
| `fields` | FieldMeta[] | Field definitions loaded lazily via `fields_get` |

**Source**: `/web/core/info` → `models[]`; field details from `execute_kw(model, 'fields_get', [])`

---

### FieldMeta

Describes a single field on a model. Loaded once per model and cached.

| Field | Type | Description |
|---|---|---|
| `name` | string | Technical field name |
| `type` | string | `char`, `integer`, `boolean`, `float`, `date`, `text`, `many2one` |
| `string` | string | Human-readable label |
| `required` | boolean | Whether the field is required |
| `readonly` | boolean | Whether the field is read-only |
| `relation` | string | Target model name (for `many2one` only) |

**Source**: `execute_kw(model, 'fields_get', [], {attributes: ['string','type','required','readonly','relation']})`

---

### Record

A single row of a model's data, as returned by `search_read`.

| Field | Type | Description |
|---|---|---|
| `id` | integer | Record ID |
| `[field_name]` | any | Field values keyed by technical name |

**Source**: `execute_kw(model, 'search_read', [[]], {fields: [...], limit: 50, offset: N})`

---

### RouterState

Client-side routing state, derived from the URL hash.

| Route Pattern | Screen | Parameters |
|---|---|---|
| `#/login` | Login page | — |
| `#/home` | Home / app menu | — |
| `#/module/:name` | Module overview | `name` = module technical name |
| `#/model/:name` | List view | `name` = model technical name |
| `#/model/:name/new` | Form view (create) | `name` = model technical name |
| `#/model/:name/:id` | Form view (edit) | `name` = model name, `id` = record ID |

## Existing Models Used (Read/Write)

| Model | Used for | Operations |
|---|---|---|
| `ir.module` | Home screen tiles | read (via `/web/core/info`) |
| `res.users` | User list + form | search_read, read, write, create, unlink |
| `res.groups` | Group list + form | search_read, read, write, create, unlink |
| `ir.rule` | Rule list + form | search_read, read, write, create, unlink |
| *(any registered model)* | Generic list/form | search_read, fields_get, read, write, create, unlink |
