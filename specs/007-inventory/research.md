# Phase 0 Research: Inventory

The spec's own `/speckit-clarify` pass (2026-09-13, two sessions) already resolved the five
highest-impact ambiguities before planning started: the `stock`/`stock_account` addon boundary,
Product Type scope (goods/service only), the Transfer `partner_id` field, the automatic-reservation
default, and the on-demand (no-scheduler) reordering-rule trigger. This document resolves the
remaining *implementation-level* unknowns needed to move from spec to data model — each framed as a
decision so a later reader can see what was rejected and why, following the format 006-human-resources
established.

## D1. Cross-addon field extension when `product` must stay account-free

**Decision**: `stock_account`'s data-seed module (`data/product_category_ext.py`) runs
`ALTER TABLE product_category ADD COLUMN IF NOT EXISTS property_stock_valuation_account_id INTEGER
REFERENCES account_account(id)` (and two sibling columns for input/output) at install time, rather
than declaring those three fields as `Many2one("account.account")` attributes on the `ProductCategory`
`BaseModel` class itself.

**Rationale**: `product.category`'s `BaseModel` class lives in the `product` addon, which per the
spec's Clarifications must carry zero dependency on `account`. But the columns must exist on
`product_category`'s table once `stock_account` is installed. `account/data/account_data.py` already
solves the identical problem for `res_partner` (`property_account_receivable_id`,
`property_account_payable_id`, …) — a table owned by `base`, extended by `account`. Copying that exact
idiom keeps the fix inside the one addon that actually needs the accounting relationship, with no
change to `product`'s own model file.

**Alternatives considered**:
- A side-table `stock.account.category.config` (one row per category) owned by `stock_account` —
  avoids raw DDL but adds a join to every valuation-account lookup and is a genuinely new pattern
  where a proven one already exists.
- Declaring the fields on `ProductCategory` guarded by `try/except` at import time — rejected; it
  would make `product`'s own model file's behaviour depend on whether `account` happens to be
  installed, which is exactly the coupling Clarifications ruled out.
- Making `stock_account`'s `ProductCategory` a *second* `BaseModel` subclass with `_inherit =
  "product.category"` — dodoo's `_inherit` mechanism (confirmed in `core/models.py`) is single-table
  inheritance for a `_type` discriminator column (used by `account.move`'s move types), not a
  cross-addon "reopen this class and add fields" mechanism like Odoo's own `_inherit`. Using it here
  would be a misapplication of a mechanism built for a different purpose.

## D2. Reservation locking under concurrent transfers

**Decision**: `StockMove.action_reserve` reserves quantity with `SELECT ... FOR UPDATE` on the
candidate `stock.quant` rows at the source location before computing how much is actually available,
inside the same `env.dml_conn()` transaction that writes the resulting `stock.move.line` rows.

**Rationale**: Two transfers confirmed at the same moment against the same location must not both
believe the same units are available — `FOR UPDATE` is Postgres's standard row-lock primitive for
exactly this "read-then-conditionally-decrement" race, and needs no new abstraction. It composes with
FR-035's separate concern (a transfer's own state going stale between confirm and validate), which
`action_set_state`'s `expected_state` check already handles independently, per ADR-030.

**Alternatives considered**: An application-level advisory lock keyed by location — rejected as an
unfamiliar primitive nowhere else in the codebase, when row-level `FOR UPDATE` is standard and
sufficient at the stated PERF-002 scale (≤100 move lines per transfer). Optimistic retry (attempt,
detect conflict, retry) — rejected as added complexity for a code path that is not a performance
bottleneck at the given scale; pessimistic locking is simpler to reason about and test.

## D3. FIFO layer consumption bookkeeping

**Decision**: `stock.valuation.layer` stores `quantity`, `unit_cost`, `value` (as posted, immutable)
and a mutable `remaining_qty`/`remaining_value` pair, updated in place as later outgoing moves consume
it. Consuming a layer never deletes or re-values it — it only decrements `remaining_qty`/
`remaining_value`, so the layer list stays a complete, append-only audit trail (needed for FR-078's
reconciliation and for the traceability requirements in US5, which apply to valuation too via the
Odoo precedent of `stock.valuation.layer.stock_move_id`).

**Rationale**: This is a direct transcription of Odoo 19.0's own `stock.valuation.layer` semantics
(open layers, FIFO consumption oldest-first, `remaining_qty` reaching zero when a layer is fully
consumed) — there is no dodoo-specific wrinkle here, just the field-level mapping onto `BaseModel`.

**Alternatives considered**: Recomputing FIFO value on demand from raw move history at report time
instead of maintaining `remaining_qty` — rejected because it would make PERF-004's 1-second target at
50,000 layers require re-deriving consumption order every time the report is opened, instead of a
single indexed read of already-materialized remaining values.

## D4. Warehouse step-configuration change after go-live

**Decision**: `StockWarehouse.action_apply_steps` (ADR-029) never deletes an existing `stock.location`
row, even one made redundant by a step-count decrease (e.g. three-step → one-step), if that location
still has any quant history. It stops using the location as a default (the picking types are
rewired), but the location itself is archived (`active = False`), not removed — matching the general
"never delete a location with movement history" edge-case expectation implied by the spec's Return
edge case (partial-package/lot returns must still resolve historical locations).

**Rationale**: A hard delete would break every historical `stock.move`/`stock.move.line` row that
references the now-gone location (`Many2one` FKs are `ondelete="RESTRICT"` per `core/fields.py`,
so a delete would in fact just fail loudly rather than silently corrupt data — but failing the
reconfiguration action outright would be a worse user experience than archiving).

**Alternatives considered**: Blocking a step-count decrease entirely once any move has touched the
intermediate location — rejected as more restrictive than Odoo 19.0's own behaviour and than the spec
requires; archiving is strictly less surprising.

## D5. `stock.move.origin` linking for multi-warehouse replenishment

**Decision**: A cross-warehouse "resupply" rule chain (ADR-032) sets a shared free-text `origin`
field on both the generated Delivery (source warehouse) and Receipt (destination warehouse) moves —
same mechanism Odoo 19.0 uses (`stock.move.origin`/`procure_method`) to let a user trace "this receipt
exists because that delivery ran" without a hard FK cycle between the two `stock.picking` rows (which
belong to different warehouses and can be validated independently, on different days).

**Rationale**: A free-text/reference-string link (rather than a `Many2one` between the two pickings)
avoids forcing validation ordering between two operationally-independent transfers, and is directly
inspectable in the traceability lookup (FR-048) alongside lot/serial/package trails, using the same
"chronological list of transfers referencing X" query shape.

**Alternatives considered**: A dedicated `stock.procurement.group` model (Odoo's actual mechanism) —
rejected as more machinery than this feature's scope needs; a shared `origin` string on the two moves
achieves the same traceability outcome without a new top-level entity, and can be upgraded to a real
procurement-group model later without breaking the traceability contract if multi-warehouse routing
grows more complex than this feature requires.

## OWASP Top 10 review (SEC-005)

- **A01 Broken Access Control**: closed by `ir.rule` company-scope domains on every model (FR-083)
  plus `require_groups(env, uid, "Inventory User", "Inventory Manager")` on every mutation/action
  route (SEC-002), following the exact `hr`/`account` idiom already reviewed for those addons. The
  valuation report additionally must never leak another company's stock value — its query is scoped
  by `company_id` at the SQL level, not filtered client-side.
- **A03 Injection**: every REST body is a Pydantic v2 model (`extra="forbid"`); every raw SQL string
  in the new addons uses parameterised `sqlalchemy.text()` calls exactly like `account_move.py` and
  `hr_contract.py` — no string-interpolated SQL anywhere in the new code, including free-text fields
  (scrap reason, count notes, product/lot names).
- **A04 Insecure Design**: the from-state precondition check (ADR-030, FR-035) closes stale/replayed
  transitions; the `SELECT ... FOR UPDATE` reservation lock (D2) closes the concurrent-double-reserve
  class of bug; FIFO's append-only layer history (D3) closes silent valuation history rewriting.
- Remaining OWASP categories (A02 Cryptographic Failures, A05 Misconfiguration, A06 Vulnerable
  Components, A07 Auth Failures, A08 Data Integrity Failures, A09 Logging Failures, A10 SSRF) carry no
  feature-specific risk beyond what 001–006 already established (session auth unchanged, no new
  third-party components per Technical Context, structured logging per FR-087/SEC-006).

## Reused precedents (no new decision needed)

- **ORM/fields**: `dodoo.core.models.BaseModel` + `dodoo.core.fields.{Char,Integer,Boolean,Float,
  Date,Datetime,Text,Many2one,One2many,Many2many,Selection,Monetary,Json}` — every new model in this
  feature is expressible with the existing field set; no new `Field` subclass is needed.
- **Migrations**: `MigrationRunner`'s additive-only `CREATE TABLE IF NOT EXISTS` /
  `ADD COLUMN IF NOT EXISTS` model — every model change in this feature is additive by construction
  (new tables, or the D1 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` extension), so no migration
  tooling change is needed.
- **Record rules**: `dodoo.addons.hr.security.seed_rules`-style idiom (a list of `{name, model,
  domain, groups, perms}` dicts fed to a shared `seed_rules` helper) — copied into
  `stock/security.py` as `officer_full`/`catalog_read`/`catalog_admin_write`-equivalent helpers scoped
  to `GROUP_USER`/`GROUP_MANAGER`.
- **REST boundary**: `dodoo.http.routing.route` + `validate(PydanticModel, body)` +
  `require_groups(env, uid, *names)` + `json_ok`/`json_err` — the exact `hr/http/employees.py`
  shape, reused verbatim for every new route in `stock/http/*.py` and `stock_account/http/valuation.py`.
- **Structured logging**: `hr/_audit.py`'s `log_transition`/`log_conflict` functions, copied to
  `stock/_audit.py` with the same signature and the same "identifiers/states only, never free text"
  rule (SEC-006 here reads as "never log scrap reasons, count notes, or partner names").
- **Menu/sidebar wiring**: the hardcoded `_render<Area>Menu`/`_<area>Has` pair in
  `web/static/app.js`, dispatched from `_renderSidebar` by hash prefix — `_renderStockMenu`/
  `_stockHas` added following `_renderHrMenu`/`_hrHas` exactly, reading a new `stock_groups` array
  from `/web/core/info` (added to `base/http/__init__.py` the same way `hr_groups`/`fleet_manager`
  were added for 006).
- **View types**: `list.js`, `form.js`, `kanban.js`, `calendar.js` already exist in
  `web/static/views/` (shipped by 006) — this feature adds no new generic view type, only new
  per-model view files (`transfer-kanban.js`, etc.) built on top of the existing ones.
- **Accounting integration surface**: `account.move`/`account.move.line`/`account.journal`/
  `account.account` fields and the `AccountMove.create/action_post/action_reverse` +
  `AccountAccount.get_balance` functions, used exactly as `account`'s own code uses them internally —
  `stock_account` is a *consumer* of this surface, not a modifier of it.
- **Testing**: `tests/hr/conftest.py`'s fixture set (`pg_container`, `db_url`, `modules_installed`,
  `env`, `company_id`, `admin_uid`) copied for `tests/product/conftest.py`,
  `tests/stock/conftest.py`, and `tests/stock_account/conftest.py`, installing `"product"`, `"stock"`,
  and `"stock_account"` respectively via `env.modules.install(name)`.
