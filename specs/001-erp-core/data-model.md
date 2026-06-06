# Data Model: Minimal ERP Core

**Feature**: `001-erp-core` | **Date**: 2026-06-06

All core tables are owned by the built-in `base` module. User-defined add-on models create
additional tables at install time; they are not catalogued here.

---

## Core Registry Tables (managed by core, not user models)

### `ir_module`

Tracks installed add-on packages and their state.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `name` | VARCHAR(128) | NOT NULL, UNIQUE | Python package name (e.g., `sale`) |
| `version` | VARCHAR(32) | NOT NULL | Current declared version |
| `installed_version` | VARCHAR(32) | | Version at last install (NULL if not installed) |
| `state` | VARCHAR(16) | NOT NULL, DEFAULT `'uninstalled'` | `uninstalled` / `installed` / `to_upgrade` |
| `depends` | TEXT | | JSON array of dependency module names |

**Indexes**: `name`

---

### `ir_model`

Registry of all models known to the system.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `name` | VARCHAR(128) | NOT NULL, UNIQUE | Dotted model name (e.g., `res.partner`) |
| `table_name` | VARCHAR(128) | NOT NULL, UNIQUE | DB table name (e.g., `res_partner`) |
| `module_id` | INTEGER | FK → `ir_module.id`, NOT NULL | Owning module |
| `description` | TEXT | | Optional human label |

**Indexes**: `name`, `table_name`

---

### `ir_model_field`

Registry of all fields declared on models.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `model_id` | INTEGER | FK → `ir_model.id`, NOT NULL | Owner model |
| `name` | VARCHAR(64) | NOT NULL | Python attribute name (e.g., `partner_id`) |
| `field_type` | VARCHAR(32) | NOT NULL | `char` / `integer` / `boolean` / `float` / `date` / `datetime` / `text` / `many2one` / `one2many` / `many2many` |
| `string` | VARCHAR(128) | | Human-readable label |
| `required` | BOOLEAN | DEFAULT FALSE | Whether NULL is rejected |
| `readonly` | BOOLEAN | DEFAULT FALSE | Whether writes are blocked via ORM |
| `default_val` | TEXT | | JSON-encoded default value |
| `relation` | VARCHAR(128) | | Target model name for relational fields |
| `relation_field` | VARCHAR(64) | | Inverse field name for One2many |
| `relation_table` | VARCHAR(128) | | Junction table name for Many2many |

**Constraints**: UNIQUE (`model_id`, `name`)
**Indexes**: `model_id`

---

### `ir_rule`

Record-level access rules (row-level security via domain injection).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `name` | VARCHAR(128) | NOT NULL | Human-readable rule name |
| `model_id` | INTEGER | FK → `ir_model.id`, NOT NULL | Model this rule applies to |
| `domain_filter` | TEXT | NOT NULL | JSON-encoded domain filter (list-of-tuples) |
| `perm_read` | BOOLEAN | DEFAULT TRUE | Apply rule on read operations |
| `perm_write` | BOOLEAN | DEFAULT TRUE | Apply rule on write operations |
| `perm_create` | BOOLEAN | DEFAULT TRUE | Apply rule on create operations |
| `perm_unlink` | BOOLEAN | DEFAULT TRUE | Apply rule on unlink operations |
| `global_rule` | BOOLEAN | DEFAULT FALSE | If TRUE, applies to all users regardless of groups |

**Indexes**: `model_id`

---

### `ir_rule_group_rel` (junction table)

| Column | Type | Constraints |
|--------|------|-------------|
| `rule_id` | INTEGER | FK → `ir_rule.id`, NOT NULL |
| `group_id` | INTEGER | FK → `res_groups.id`, NOT NULL |

**PK**: (`rule_id`, `group_id`)

---

### `ir_session`

Server-side session store for authenticated users.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `token` | VARCHAR(64) | NOT NULL, UNIQUE | Cryptographically random token (≥ 128 bits entropy) |
| `user_id` | INTEGER | FK → `res_users.id`, NOT NULL | Owning user |
| `create_date` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Session creation timestamp |
| `expire_date` | TIMESTAMPTZ | NOT NULL | Session expiry (configurable, default 8h from creation) |

**Indexes**: `token` (lookup on every request), `user_id`, `expire_date` (cleanup)

---

## Base Module User / Group Tables

### `res_groups`

Named sets of permissions. Users inherit rules bound to their groups.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `name` | VARCHAR(128) | NOT NULL | Group display name (e.g., `Administrator`) |
| `full_name` | VARCHAR(256) | | Qualified name including category (e.g., `Technical / Administrator`) |
| `category` | VARCHAR(128) | | Logical category for grouping in UIs |

---

### `res_users`

Principals that can authenticate and act on behalf of a human or system.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, auto | Surrogate key |
| `login` | VARCHAR(64) | NOT NULL, UNIQUE | Authentication username / email |
| `password_hash` | VARCHAR(256) | NOT NULL | Argon2id hash; plaintext NEVER stored |
| `name` | VARCHAR(128) | NOT NULL | Display name |
| `active` | BOOLEAN | DEFAULT TRUE | Inactive users cannot authenticate |

**Indexes**: `login`, `active`
**Security**: `password_hash` column MUST NOT appear in any log or API response.

---

### `res_users_groups_rel` (junction table)

| Column | Type | Constraints |
|--------|------|-------------|
| `user_id` | INTEGER | FK → `res_users.id`, NOT NULL |
| `group_id` | INTEGER | FK → `res_groups.id`, NOT NULL |

**PK**: (`user_id`, `group_id`)

---

## Field Type → PostgreSQL Column Type Mapping

| Field Type | PostgreSQL Type | Notes |
|------------|----------------|-------|
| `Char` | `VARCHAR(size)` | Default size 255 |
| `Text` | `TEXT` | Unbounded |
| `Integer` | `INTEGER` | 32-bit signed |
| `Boolean` | `BOOLEAN` | |
| `Float` | `DOUBLE PRECISION` | |
| `Date` | `DATE` | |
| `Datetime` | `TIMESTAMP WITH TIME ZONE` | Always UTC |
| `Many2one` | `INTEGER` | FK to related table; ON DELETE RESTRICT |
| `One2many` | *(no column)* | Virtual; FK is on the related model |
| `Many2many` | *(no column)* | Junction table auto-created as `{model1}_{model2}_rel` |

---

## Single-Table Inheritance Layout

When a child model `B` extends parent model `A`:

- `B` shares table `a` (parent's table)
- A `_type` VARCHAR(128) column is added to `a` if not present
- `_type` stores the model name (`'a'` for parent rows, `'b'` for child rows)
- Child-specific fields are added as additional columns in `a` via `ALTER TABLE`
- Queries on model `A` return all rows; queries on model `B` add `WHERE _type = 'b'`

```
Table: a
  id         INTEGER PK
  name       VARCHAR(255)        ← parent field
  _type      VARCHAR(128)        ← discriminator (added automatically)
  b_extra    INTEGER             ← child B field (added at B install time)
```

---

## Validation Rules

- `res_users.login`: MUST be non-empty; MUST be unique (case-insensitive at application layer)
- `ir_rule.domain_filter`: MUST be valid JSON; MUST deserialise to a list of 3-tuples
- `ir_session.token`: MUST be generated via `secrets.token_urlsafe(32)` (256 bits, URL-safe)
- `ir_session.expire_date`: MUST be in the future at session creation; expired sessions are
  rejected at the auth middleware layer before any handler executes
- Many2one fields: `ON DELETE RESTRICT` by default; cascade must be explicitly declared
- `_type` discriminator: MUST match a registered model name; orphan values produce a warning
  at startup, not a hard error (forward-compatibility)

---

## State Transitions

### Module state machine

```
uninstalled ──install──► installed
installed   ──upgrade──► to_upgrade ──upgrade_complete──► installed
installed   ──uninstall──► uninstalled  (future milestone)
```

### Session lifecycle

```
[no session] ──authenticate──► active
active       ──expire──►       expired (cleaned up by background task or next request)
active       ──logout──►       deleted (token invalidated immediately)
expired      ──authenticate──► active (new session)
```
