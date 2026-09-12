# Implementation Plan: Inventory

**Branch**: `007-inventory` | **Date**: 2026-09-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-inventory/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Deliver three addons — `dodoo/addons/product/` (catalog: categories, units of measure, templates,
attributes, variants), `dodoo/addons/stock/` (warehouses, locations, operation types, transfers/stock
moves, physical inventory, lots/serials, packages, putaway/storage categories, routes/reordering
rules, scrap), and `dodoo/addons/stock_account/` (costing methods, stock valuation layers, journal
posting into `account`) — reproducing the Odoo 19.0 `product`, `uom`, `stock`, and `stock_account`
addons' behaviour on dodoo's existing stack (FastAPI + SQLAlchemy Core async `BaseModel` + Pydantic v2
whitelist validation + `ir.rule` record rules + the vanilla-JS SPA). `product` depends only on
`base`/`web`; `stock` depends on `product` + `base` + `web` + `localization` (005) with **no**
dependency on `account`; `stock_account` depends on `stock` + `account` (003), mirroring Odoo's own
split exactly (per spec Clarifications). Reused precedents from 001–006: the `BaseModel`/`Field` ORM,
`ir.rule` company-scoped record rules, the REST-route + `validate()`/`require_groups()` boundary
pattern, the hardcoded `_render<Area>Menu` sidebar-menu dispatch in `web/static/app.js`, the
list/form/kanban/calendar view types (already shipped by 006 — no new view type needed), and the
state-machine + structured-transition-logging idiom from `hr_contract.py`/`hr/_audit.py`. Six ADRs
are filed (029–034) for the non-trivial designs: warehouse step→topology generation, the
transfer/reservation/backorder state engine, putaway/storage-category capacity resolution, route/rule
replenishment resolution, the costing-method valuation engine (including the cross-addon
`ALTER TABLE` field-extension pattern — precedented by `account`'s own extension of `res_partner` —
needed to attach stock-valuation account properties, `product.category.costing_method`, and
`product.product`'s `tracking`/`stock_avg_cost` columns from `stock`/`stock_account` without giving
`product` a dependency on `stock` or `account`), and the import-time function-wrapping mechanism
`stock_account` uses to trigger valuation from `stock`'s single move-completion choke point without
`stock` ever depending on or referencing `stock_account`.

## Technical Context

**Language/Version**: Python 3.12 (matches 001–006; no change).

**Primary Dependencies**: FastAPI (HTTP routing via `dodoo.http.routing.route`), SQLAlchemy Core
async + asyncpg (`dodoo.core.models.BaseModel` / `dodoo.core.fields`), Pydantic v2
(`validators.py` whitelist models, `extra="forbid"`), pytest + pytest-asyncio + testcontainers
(tests). **Zero new runtime dependencies** — the same stack as 001-erp-core through
006-human-resources.

**Storage**: PostgreSQL. New tables — `product`: `product_category`, `uom_category`, `uom_uom`,
`product_template`, `product_attribute`, `product_attribute_value`,
`product_template_attribute_line`, `product_template_attribute_value` (join of line × value, needed
to know which values are actually selected per line), `product_product`,
`product_product_attribute_value_rel` (M2M: which attribute values a given variant carries).
`stock`: `stock_warehouse`, `stock_location`, `stock_picking_type`, `stock_picking`, `stock_move`,
`stock_move_line`, `stock_quant`, `stock_lot`, `stock_quant_package`, `stock_package_type`,
`stock_storage_category`, `stock_storage_category_location_rel` (M2M), `stock_putaway_rule`,
`stock_route`, `stock_route_product_rel` / `stock_route_category_rel` / `stock_route_warehouse_rel`
(M2M), `stock_rule`, `stock_warehouse_orderpoint`, `stock_scrap`, plus one column added to the
existing `product_product` table via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (the same
`account`→`res_partner` precedent, one dependency level down): `tracking` (VARCHAR(64), default
`'none'`). `stock_account`: `stock_valuation_layer`, plus four columns added to the existing
`product_category` table the same way: `costing_method` (VARCHAR(64), default `'standard'`),
`property_stock_valuation_account_id`, `property_stock_input_account_id`,
`property_stock_output_account_id` (all three `INTEGER REFERENCES account_account(id)`); plus one
column added to `product_product`: `stock_avg_cost` (`NUMERIC(20,6)`, default 0); and one new
`account_journal` row ("Inventory Valuation", type `general`).

**Testing**: `tests/product/`, `tests/stock/`, `tests/stock_account/` (unit — UoM conversion math,
variant-generation Cartesian product, transfer state-transition guards, putaway/storage capacity
resolution, FIFO layer consumption math; integration — full receipt→reserve→validate→backorder
flows, putaway redirection end to end, route-driven replenishment, valuation posting → `account.move`
→ `AccountAccount.get_balance` reconciliation, company-scope record-rule enforcement), plus
`tests/benchmarks/test_inventory_perf.py` (PERF-001…004) and `tests/e2e/test_inventory_ui.py`
(Playwright + the shared `test_web_ui_a11y.py` WCAG checks) — mirroring 006's exact test-directory
and fixture (`pg_container`/`db_url`/`modules_installed`/`env`/`company_id`/`admin_uid`) conventions
from `tests/hr/conftest.py`. Per the existing `[[accounting-test-isolation]]` project memory,
`tests/stock_account/test_valuation_report.py` (which reads `AccountAccount.get_balance` ledger
totals) must be run standalone, not batched with other DB-sharing test files, exactly like
`tests/accounting`'s report/balance tests.

**Target Platform**: Existing dodoo web server (same Linux/Windows dev + CI targets as 001–006); no
new deployment target.

**Project Type**: Web service + vanilla-JS SPA (existing monolith; three new addons plugged into the
existing FastAPI app + `web/static/app.js` sidebar).

**Performance Goals**: PERF-001 catalog list/search first page (50 of ≤20,000 variants) < 500 ms via
a composite index on `(company_id, category_id, product_type)` plus a trigram/`ILIKE` index on
`name`/`barcode`. PERF-002 transfer confirm/reservation (≤100 move lines) < 500 ms via a covering
index on `stock_quant (product_id, location_id, lot_id, package_id)` (the reservation query's exact
shape) and batching move-line reservation in one query per transfer rather than per line. PERF-003
on-hand/forecast computation (≤100,000 quants for one product) < 300 ms via
`stock_quant (product_id)` index + a materialized-at-read aggregate (no per-request full scan of
`stock_move`). PERF-004 valuation report (≤50,000 open layers) < 1 s via
`stock_valuation_layer (product_id, remaining_qty)` partial index (`WHERE remaining_qty <> 0`) so
FIFO's "remaining layers" query never scans consumed layers.

**Constraints**: No new runtime dependencies. Migrations are additive-only (`MigrationRunner`,
`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`) — a destructive change is not available,
so every model change across this feature's iteration must be additive. No per-request transaction
spans multiple `create`/`write` calls (each commits independently, per 006's research D1) — every
multi-row workflow (validate a transfer's move lines + update quants; post a valuation layer +
create/post its journal entry) is written as an idempotent, re-runnable sequence guarded by
existence checks, exactly like `account_move.py::action_post`'s pattern of re-checking state before
mutating. `product` and `stock` MUST carry no dependency on `account` (Clarifications) — the three
stock-valuation account properties on `product.category` are added by `stock_account` via the
`ALTER TABLE` idiom, never as a `Many2one` field declared inside the `product` addon's own model
class.

**Scale/Scope**: 3 addons, 23 new `BaseModel` classes across `product` + `stock`, 1 new model
(`stock.valuation.layer`) + 3 extension columns in `stock_account`, ~89 functional requirements
(FR-001…FR-089 plus FR-024a/FR-063a), 8 user stories (P1×3: US1–US3; P2×3: US4–US6; P3×2: US7–US8),
6 ADRs (029–034), 9 contract files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. Code Quality**: Same linters/formatters as 001–006 (already configured in CI for the
  `dodoo/` package and `tests/`); no new tooling. Naming follows the established
  `snake_case` model/table convention (`stock_picking`, `stock_move_line`, …) and the
  `dodoo/addons/<name>/{models,http,data,static}` file layout used by `hr`/`account`.
- [X] **II. Testing**: Unit tests cover UoM conversion, variant generation, transfer state guards,
  putaway/storage resolution, and FIFO consumption math (pure logic, no DB). Integration tests cover
  every cross-model workflow in FR-023…FR-089 (transfer lifecycle, putaway redirection, replenishment,
  valuation posting/reconciliation, company-scope record rules) against a real Postgres test
  container, per `tests/hr/conftest.py`'s fixtures. E2E tests cover the 8 user stories' primary flows
  plus WCAG per ACC-001…004. Coverage thresholds match 001–006's CI gate (≥80% unit, 100% on
  transfer/valuation critical paths).
- [X] **III. Security**: SEC-001…SEC-007 map directly to `validators.py` Pydantic whitelist models
  (`extra="forbid"`) on every REST route, `require_groups(env, uid, "Inventory User", "Inventory
  Manager")` gating on every mutation/action route, and `ir.rule` company-scope domains
  (`$company_ids`) on every model per FR-083. OWASP review (SEC-005) is scheduled before
  implementation, focused on A01 (cross-company stock/valuation exposure — same class of risk as
  006's SEC-003) and A04 (quantity/valuation manipulation via stale-state replay — closed by the
  FR-035 from-state precondition check, same mechanism as `hr_contract.py`'s
  `action_set_state(expected_state=...)`). Valuation posting reuses `AccountMove.action_post`'s own
  balance-integrity/authorization path (SEC-006) rather than writing ledger balances directly.
- [X] **IV. Performance**: PERF-001…005 targets are stated above with the concrete index/query
  strategy for each; `tests/benchmarks/test_inventory_perf.py` runs them in CI alongside 001–006's
  existing benchmarks (PERF-005 requires no regression there).
- [X] **V. Documentation**: ADR-029…034 filed below for every non-trivial design decision
  (warehouse topology generation, transfer/reservation state engine, putaway/storage-category
  resolution, route/rule replenishment resolution, costing-method valuation engine +
  cross-addon account-property extension, and the cross-addon action-hooking mechanism for
  triggering valuation without a reverse dependency). Inline comments follow the WHY-only policy
  already demonstrated in `hr_contract.py`/`account_move.py` (state-machine rationale, rounding
  rationale — never restating field names).
- [X] **VI. Accessibility**: ACC-001…004 restate WCAG 2.1 AA targets; no new view type is needed —
  Inventory reuses the list/form/kanban/calendar types already shipped by 006, so their existing
  accessibility work (keyboard nav, ARIA labelling, RTL tab order) is inherited rather than
  re-implemented. The one new interaction surface (drag-free keyboard-operable putaway/reordering
  editors, FR the same as HR's Kanban stage-move keyboard alternative) is scoped in `quickstart.md`.
- [X] **VII. Dependencies**: Zero new dependencies (Technical Context above). `product`, `stock`,
  and `stock_account`'s only "dependency" additions are on each other and on the existing `base`,
  `web`, `localization`, and `account` addons — no third-party package, so no CVE audit or lock-file
  change is needed beyond what 001–006 already cover.
- [X] **VIII. CI/CD**: Reuses the existing CI pipeline (lint, format, unit/integration/e2e/benchmark
  test stages) already covering `hr`/`account`/`fleet`; the three new addons' test directories plug
  into the same `pytest` invocation with no new CI configuration required beyond adding the
  directories to the existing test-discovery glob (already recursive per `tests/__init__.py`).
- [X] **IX. Observability**: FR-087 mandates a structured JSON log entry (correlation ID, actor,
  record, from/to state) for every workflow transition, implemented via a new
  `dodoo/addons/stock/_audit.py` mirroring `hr/_audit.py`'s `log_transition`/`log_conflict`
  functions exactly (same payload shape, same WARNING-level conflict logging, same SEC-006 "no PII
  in logs" rule — here read as "no free-text scrap/count reason text in logs").

*Initial gate: PASS. Post-design re-check: PASS — no new violations introduced in Phase 1 (data
model and contracts stay within the patterns validated above); see Complexity Tracking for the two
decisions that needed explicit justification rather than being a bare gate pass.*

## Architecture Decision Records

**ADR-029: Warehouse step-configuration → location/operation-type topology generation**

- **Decision**: `stock.warehouse` stores `reception_steps` (`one_step`/`two_steps`/`three_steps`) and
  `delivery_steps` (same three values). Creating or reconfiguring a warehouse runs a deterministic
  generator (`StockWarehouse.action_apply_steps(env, warehouse_id)`) that ensures the exact set of
  child `stock.location` rows for that configuration exist (`WH/Stock` always; `WH/Input` +
  `WH/Quality Control` added for two/three-step receipts; `WH/Output` + `WH/Packing` added for
  two/three-step deliveries) and ensures the corresponding `stock.picking.type` rows' default
  source/destination locations point at the right link in the chain (e.g. three-step receipts:
  Receipts → Input, an internal "Input to Quality" type → Quality, another internal "Quality to
  Stock" type → Stock). Re-running the generator after a config change is idempotent: it only
  creates locations/operation-types that don't already exist by name+warehouse and only rewires
  default locations, never deletes a location that already holds a quant.
- **Rationale**: Matches Odoo 19.0's `stock.warehouse` `_get_locations_values`/route-generation
  behaviour (FR-013/014) exactly, and keeps location/operation-type creation as plain `BaseModel`
  rows (no special-cased "system location" flag needed elsewhere) — every later feature (putaway,
  routes, reordering) just references locations/operation-types like any other.
  `MigrationRunner`'s additive-only migration model means this generator must be re-runnable, not a
  one-shot install hook, since a warehouse's step configuration can change after go-live (FR-014).
- **Alternatives rejected**: Hardcoding a fixed one-step warehouse (no step configuration) — rejected
  because FR-014 explicitly requires multi-step support and Odoo 19.0 parity was asked for. Modelling
  steps as a free-form `stock.route`-only concept with no warehouse-level shortcut field — rejected as
  needless complexity for the common case; the generator still produces plain `stock.route`/`stock.rule`
  rows under the hood for consistency with US6's route model, it's just that the warehouse form
  drives that generation instead of requiring the user to hand-build the route.

**ADR-030: Transfer / stock-move reservation and backorder state engine**

- **Decision**: `stock.picking.state` is a **derived** value computed from its moves' states, not a
  stored field written directly by user action (mirrors Odoo's `_compute_state`): `draft` if all
  moves are draft, `waiting` if not all moves are reservable, `confirmed`/`ready` once reservation
  succeeds fully, `done` once all moves are done, `cancelled` once all moves are cancelled. Legal
  manual transitions live on `stock.move` (not the picking) via
  `StockMove.action_set_state(env, ids, target, uid, expected_state)` — the exact
  `hr_contract.py::action_set_state` shape (from-state precondition check → `DodooError
  transfer_state_conflict` + `log_conflict` on mismatch, else `log_transition` on success). Confirming
  a picking calls `StockMove.action_reserve` for each of its moves, which attempts to lock
  (`SELECT ... FOR UPDATE`) and decrement available `stock.quant` rows at the source location up to
  the demanded quantity, creating/updating `stock.move.line` rows for the reserved portion; a move
  with partial or zero reservation stays in `waiting`. Validating a picking with under-reserved moves
  calls `StockPicking.action_create_backorder(env, picking_id)`, which clones the picking (same
  operation type, partner, new moves for exactly the unmet remainder) and marks the original done for
  only its actually-moved quantity.
- **Rationale**: A derived picking state (rather than an independently-writable one) makes FR-035's
  concurrency guard trivial to reason about — there is exactly one place (`stock.move`'s row) where a
  stale-state race can occur, closed by the same `expected_state` mechanism `hr_contract.py` already
  proved out. `SELECT ... FOR UPDATE` on the reservation query is the standard way to make concurrent
  reservation of the same quant safe without a new locking primitive.
- **Alternatives rejected**: A single stored `state` column on `stock.picking` written directly by
  each action — rejected because it duplicates truth (the moves' states) and reopens exactly the
  "two truths can disagree" bug class 006's contract-state ADR was written to avoid. Optimistic
  concurrency via a `version` column — rejected per 006's precedent (FR-067a's plain from-state
  check was accepted there without a version token; no reason to diverge here).

**ADR-031: Putaway rule and storage-category capacity resolution**

- **Decision**: Resolving a move line's destination (FR-057) is a pure function
  `StockPutawayRule.resolve_destination(env, product_id, source_location_id)` returning either the
  original destination (no applicable rule, or no eligible destination has capacity) or the first
  matching rule's destination. Rule matching order: product-specific rules before category rules
  (FR-058), then declaration order within the same specificity. Capacity check
  (`StockStorageCategory.has_capacity(env, location_id, incoming_qty, incoming_package)`) is
  evaluated per candidate destination by counting existing quants/packages at that location against
  the storage category's `max_weight` / `max_packages` / same-product-or-lot policy — a location
  with **no** storage category assigned always has unlimited capacity (Odoo 19.0 default).
- **Rationale**: Keeping resolution as a single pure query-and-decide function (no writes) means it
  can be unit-tested without a transfer at all, and reused identically from both the receipt-time
  move-line creation path and a "preview putaway" read-only endpoint if one is ever wanted.
- **Alternatives rejected**: Encoding capacity as a boolean flag recomputed and cached on
  `stock.location` on every quant change — rejected as a cache-invalidation hazard for no measured
  performance benefit at the stated PERF targets (putaway resolution is O(number of eligible
  destination locations for one product), not a hot aggregate path).

**ADR-032: Route/rule replenishment resolution**

- **Decision**: `stock.rule` rows form a directed chain via `location_dest_id` of one rule matching
  `location_src_id` of the next (Odoo's pull-rule chaining). `StockRoute.get_applicable_route(env,
  product_id, warehouse_id)` resolves the single applicable route for a product (product-level route
  override, else category-level, else warehouse default). `StockWarehouseOrderpoint.run_reordering(env,
  orderpoint_ids=None)` — the FR-063a on-demand action — computes each orderpoint's forecasted
  quantity, and for every one below its minimum, walks its route's rule chain from the
  warehouse-internal end backward to generate one `stock.picking` per rule hop (a same-warehouse
  multi-step chain yields internal transfers; a cross-warehouse "resupply" rule yields a Delivery at
  the source warehouse and a Receipt at the destination warehouse, linked by a shared
  `stock.move.origin` reference through an intermediate transit location — Odoo's own inter-warehouse
  mechanism). Per the spec Clarifications, a rule whose chain terminates at the Vendor location (no
  Purchase app) simply becomes a Receipt-type transfer sourced from Vendor, valued at the product's
  current cost. Duplicate-suppression (FR-065) is a plain existence check: skip an orderpoint if an
  incoming, not-yet-done transfer already targeting its location already covers the deficit.
- **Rationale**: Chaining via matching source/destination locations (rather than an explicit
  "next rule" pointer) is exactly Odoo 19.0's own `stock.rule` model, so the behaviour (including
  multi-warehouse resupply) is reproduced faithfully with a small, testable resolution function
  instead of a bespoke graph structure.
- **Alternatives rejected**: An explicit `next_rule_id` linked-list field on `stock.rule` — rejected
  as redundant with location matching and harder to keep consistent when a route is edited (two rules
  could silently point at different locations than their `next_rule_id` implies).

**ADR-033: Costing-method valuation engine and `stock_account`/`account` integration**

- **Decision**: `product.category.costing_method` (Selection: `standard`/`average`/`fifo`) and its
  three sibling account properties (`property_stock_valuation_account_id`,
  `property_stock_input_account_id`, `property_stock_output_account_id`) are **all four** added to
  the **existing** `product_category` table by `stock_account`'s own data-seed module via
  `ALTER TABLE product_category ADD COLUMN IF NOT EXISTS ...` — not declared as `Field`s on
  `product`'s own `ProductCategory` model class, since even the plain `costing_method` enum is
  meaningless (and unused) until `stock_account` exists. `stock` similarly adds a `tracking`
  (none/lot/serial) column to `product_product` via the same idiom (one dependency level down), and
  `stock_account` adds a `stock_avg_cost` column to `product_product` for average-costing's running
  value. `StockValuationLayer.value_move(env, move_id)` (called once per validated `stock.move` of an
  `is_storable` product) reads `costing_method` and, for `standard`, values at the product's plain
  `product.template.standard_price`; for `average`, recomputes `stock_avg_cost`; for `fifo`, opens/
  consumes `stock.valuation.layer` rows oldest-first (`ORDER BY create_date`), splitting a layer when
  the outgoing quantity is smaller than its `remaining_qty`. Every layer immediately calls
  `AccountMove.create(...) → insert account.move.line rows → AccountMove.action_post(...)`
  (the exact `move_type="entry"` flow already used by `account`'s own manual-entry path), crediting/
  debiting the category's three account properties — the identical `ALTER TABLE` idiom
  `account/data/account_data.py` already uses to add `property_account_receivable_id` etc. to
  `res_partner` (a table it does not own). A default seed reuses the already-seeded chart-of-accounts
  code `1100` ("Inventory", `asset_current`) as the default valuation account and adds two new interim
  accounts plus one new `general`-type "Inventory Valuation" journal (account_journal has no dedicated
  stock/inventory journal type — none is needed, per the fork research). Because these
  `ALTER TABLE`-added columns are never registered in `ProductCategory._fields` (confirmed:
  `account` itself never registers `res_partner`'s equivalent `property_account_*` columns either —
  `BaseModel.write()` silently drops unknown keys), reading/writing them goes through a dedicated
  raw-SQL REST action (`GET`/`POST /stock_account/category/{id}/configure`), not a generic
  `product.category.write()` call — see `contracts/stock-valuation.md`.
- **Rationale**: The `ALTER TABLE`-on-a-foreign-table idiom is not a new pattern invented for this
  feature — it is the *only* precedent in the codebase for "addon B needs a field on addon A's model
  that only makes sense once B is installed," and it is exactly this feature's situation (Clarifications:
  `product` must stay account-free while its categories still need account properties once
  `stock_account` is installed). Reusing `AccountMove.action_post` end to end (rather than writing
  `account_move`/`account_move_line` rows and flipping `state='posted'` directly) means valuation
  postings get the balance-invariant check, sequence naming, and immutability guarantees for free
  (SEC-006) instead of re-implementing them.
- **Alternatives rejected**: Storing the three account properties on a brand-new
  `stock.account.category.config` model instead of extending `product_category` — rejected as an
  unnecessary indirection (an extra join on every valuation lookup) when the `ALTER TABLE` idiom is
  already proven safe by `account`'s own use on `res_partner`. Giving `product` a soft/optional
  dependency on `account` — rejected outright; the Clarifications session already closed this
  question in favour of `stock_account` as the sole dependency holder.

**ADR-034: Cross-addon action hooking — triggering valuation from `stock` without a reverse
dependency**

- **Decision**: `stock`'s three "a move becomes done" paths (transfer validation, physical-inventory
  count application, scrap confirmation) are all implemented to converge on one choke point,
  `StockMove.action_set_state(env, [move_id], "done", uid=uid)`, rather than each writing
  `state="done"` independently. `stock_account/__init__.py` wraps that single classmethod at Python
  import time: the wrapper calls the original, and only on success (and only for `is_storable`
  products) calls `StockValuationLayer.value_move`. The wrap is applied unconditionally at import
  time — a deployment that never imports `dodoo.addons.stock_account` never applies it, so `stock`'s
  own source carries no reference to `stock_account` anywhere (research.md D6).
- **Rationale**: dodoo has no hook/event/signal registry (confirmed by search of the codebase — no
  existing addon needs one; every prior cross-addon interaction, HR↔Fleet included, is a plain FK
  read, never behavioural interception). Odoo's own `_inherit` achieves this effect through a registry
  rebuilding every model's MRO from all installed modules; dodoo's `_inherit` is deliberately narrower
  (a single-table `_type` discriminator only, per `core/models.py`). Import-time function wrapping
  reproduces the needed effect with zero new core infrastructure while preserving the *direction* of
  the dependency at the behavioural level, not just the schema level — the same one-way guarantee
  ADR-033 established for data.
- **Alternatives rejected**: A generic hook/event-bus in `dodoo/core/` — disproportionate new
  infrastructure for this feature's single integration point. `stock` dynamically importing an
  optional callback module by string name (`try/except ImportError`) — rejected because it still
  requires `stock`'s own source to know and reason about `"stock_account"`, the soft form of exactly
  the coupling Clarifications ruled out. A periodic reconciliation job — rejected: valuation must post
  atomically with the move (FR-072/075), and polling reopens the "no scheduler" problem this project
  otherwise avoids (ADR-032/FR-063a).

## Project Structure

### Documentation (this feature)

```text
specs/007-inventory/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── stock-products.md        # product/uom/variants (US1)
│   ├── stock-warehouses.md      # warehouses/locations/operation types (US2)
│   ├── stock-transfers.md       # receipts/deliveries/internal/returns (US3)
│   ├── stock-inventory.md       # physical inventory adjustments (US4)
│   ├── stock-traceability.md    # lots/serials/packages (US5)
│   ├── stock-routes.md          # putaway/storage/routes/reordering (US6)
│   ├── stock-scrap.md           # scrap (US7)
│   ├── stock-valuation.md       # costing methods + stock_account (US8)
│   └── security-groups.md       # Inventory User/Manager groups + record rules
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
dodoo/addons/product/
├── __init__.py                       # imports http + models
├── __manifest__.py                   # {"name": "Product", "depends": ["base", "web"], "application": False}
├── security.py                       # no dedicated groups — product records are readable by any
│                                      #   authenticated user; write access gated by Inventory groups
│                                      #   defined in stock/security.py (product has no app-level group
│                                      #   of its own, matching Odoo, where product lives inside the
│                                      #   Inventory app's Settings)
├── validators.py                     # ProductCategoryCreate, UomCategoryCreate, UomCreate,
│                                      #   ProductTemplateCreate, AttributeCreate, AttributeLineSet, ...
├── models/
│   ├── __init__.py
│   ├── product_category.py           # product.category (no costing/account fields — those are
│   │                                  #   ALTER TABLE extensions added by stock_account, ADR-033)
│   ├── uom.py                        # uom.category, uom.uom (+ conversion helper)
│   ├── product_template.py           # product.template
│   ├── product_attribute.py          # product.attribute, product.attribute.value,
│   │                                  #   product.template.attribute.line/value
│   └── product_product.py            # product.product (+ variant-generation, FR-006)
├── http/
│   ├── __init__.py
│   └── products.py                   # REST actions: apply-attribute-lines (regenerate variants),
│                                      #   search/barcode lookup
├── data/
│   ├── __init__.py
│   ├── ir_model_sync.py              # sync_ir_model for product.* models
│   ├── indexes.py                    # PERF-001 covering indexes
│   └── seed.py                       # FR-089: UoM categories/units, sample categories/products
└── static/
    └── views/
        ├── product-template-form.js
        ├── product-variant-list.js
        └── product-category-list.js  # (list/form/kanban reuse the generic view types from 006)

dodoo/addons/stock/
├── __init__.py                       # imports http + models; post_install seeds warehouse/UoM demo data
├── __manifest__.py                   # {"name": "Inventory", "depends": ["product", "base", "web",
│                                      #   "localization"], "application": True}
├── security.py                       # GROUP_USER = "Inventory User", GROUP_MANAGER = "Inventory Manager"
│                                      #   (2-level nesting, same shape as hr/security.py)
├── validators.py                     # WarehouseCreate, TransferValidate, CountApply, ScrapConfirm,
│                                      #   PutawayRuleCreate, OrderpointCreate, RunReordering, ...
├── models/
│   ├── __init__.py
│   ├── stock_warehouse.py            # stock.warehouse (+ action_apply_steps, ADR-029)
│   ├── stock_location.py             # stock.location
│   ├── stock_picking_type.py         # stock.picking.type
│   ├── stock_picking.py              # stock.picking (+ derived state, backorder, return — ADR-030)
│   ├── stock_move.py                 # stock.move (+ action_reserve/action_set_state — ADR-030)
│   ├── stock_move_line.py            # stock.move.line
│   ├── stock_quant.py                # stock.quant (+ on-hand/forecast aggregation); apply_count
│   │                                  #   routes its adjustment move through
│   │                                  #   StockMove.action_set_state(..., "done", ...) — the single
│   │                                  #   choke point stock_account hooks (ADR-034)
│   ├── stock_lot.py                  # stock.lot
│   ├── stock_package.py              # stock.quant.package, stock.package.type
│   ├── stock_storage_category.py     # stock.storage.category (+ has_capacity, ADR-031)
│   ├── stock_putaway_rule.py         # stock.putaway.rule (+ resolve_destination, ADR-031)
│   ├── stock_route.py                # stock.route, stock.rule (+ get_applicable_route, ADR-032)
│   ├── stock_orderpoint.py           # stock.warehouse.orderpoint (+ run_reordering, ADR-032)
│   ├── stock_scrap.py                # stock.scrap; confirm routes its move through
│   │                                  #   StockMove.action_set_state(..., "done", ...) (ADR-034)
│   └── product_product_ext.py        # set_tracking(env, product_id, tracking, uid) guard — the
│                                      #   only write path for the `tracking` column stock adds to
│                                      #   product_product (D1, one dependency level below ADR-033)
├── _audit.py                         # log_transition/log_conflict (mirrors hr/_audit.py exactly)
├── http/
│   ├── __init__.py
│   ├── warehouses.py                 # warehouse/location/operation-type CRUD actions
│   ├── transfers.py                  # confirm/reserve/validate/cancel/return actions (FR-023…036)
│   ├── inventory.py                  # count list + apply-count action (FR-037…042)
│   ├── traceability.py               # lot/serial/package traceability lookups (FR-048/054)
│   ├── routes.py                     # putaway/storage/route/orderpoint CRUD + run-reordering action
│   └── scrap.py                      # scrap confirm action
├── data/
│   ├── __init__.py
│   ├── ir_model_sync.py
│   ├── groups.py                     # seed_groups() for Inventory User/Manager
│   ├── rules.py                      # ir.rule specs (officer_full-style per FR-081/082)
│   ├── indexes.py                    # PERF-002/003 covering indexes
│   ├── product_product_ext.py        # ALTER TABLE product_product ADD COLUMN IF NOT EXISTS tracking
│   │                                  #   VARCHAR(64) DEFAULT 'none' (D1) — run before groups/rules
│   └── seed.py                       # FR-089: default warehouse + locations/operation types
└── static/
    ├── stock-menu.js                 # STOCK_MENU export (mirrors hr-menu.js shape)
    └── views/
        ├── transfer-kanban.js        # by-operation-type/state kanban (FR-033, reuses kanban.js)
        ├── transfer-form.js
        ├── inventory-count-list.js
        └── traceability-view.js

dodoo/addons/stock_account/
├── __init__.py                       # imports http + models; wraps StockMove.action_set_state at
│                                      #   import time to trigger value_move on "done" (ADR-034/D6);
│                                      #   post_install seeds COA/journal extension
├── __manifest__.py                   # {"name": "Inventory Accounting", "depends": ["stock", "account"],
│                                      #   "application": False}
├── validators.py                     # (none beyond re-exporting stock's require_groups pattern —
│                                      #   valuation has no user-facing mutation endpoints beyond
│                                      #   read-only reporting; posting is triggered by stock moves)
├── models/
│   ├── __init__.py
│   └── stock_valuation_layer.py      # stock.valuation.layer (+ value_move, ADR-033)
├── http/
│   ├── __init__.py
│   └── valuation.py                  # GET valuation report (FR-077/078)
└── data/
    ├── __init__.py
    ├── product_category_ext.py       # ALTER TABLE product_category ADD COLUMN IF NOT EXISTS
    │                                  #   costing_method, property_stock_valuation_account_id,
    │                                  #   property_stock_input_account_id,
    │                                  #   property_stock_output_account_id (ADR-033)
    ├── product_product_ext.py        # ALTER TABLE product_product ADD COLUMN IF NOT EXISTS
    │                                  #   stock_avg_cost NUMERIC(20,6) DEFAULT 0 (ADR-033)
    ├── indexes.py                    # PERF-004 partial index on remaining_qty
    └── seed.py                       # default valuation/interim accounts + "Inventory Valuation" journal

# EDIT (existing files, not new addons):
dodoo/addons/web/static/app.js        # + _renderStockMenu/_stockHas (mirrors _renderHrMenu/_hrHas),
                                       #   + `#/inventory` hash-prefix dispatch branch in _renderSidebar,
                                       #   reuses existing kanban.js/calendar.js — no new view-type file
dodoo/addons/base/http/__init__.py    # + `stock_groups` in the /web/core/info response, same pattern
                                       #   as the existing `hr_groups`/`fleet_manager` fields

tests/product/
├── __init__.py
├── conftest.py                       # mirrors tests/hr/conftest.py, installs "product"
├── test_uom_conversion.py
├── test_variant_generation.py
└── test_access_rules.py

tests/stock/
├── __init__.py
├── conftest.py                       # installs "stock" (transitively "product")
├── test_warehouse_topology.py        # ADR-029
├── test_transfer_reservation.py      # ADR-030 (incl. concurrency/backorder)
├── test_inventory_adjustment.py
├── test_lots_serials.py
├── test_packages.py
├── test_putaway_storage.py           # ADR-031
├── test_routes_reordering.py         # ADR-032
├── test_scrap.py
├── test_access_rules.py
└── test_migrations.py

tests/stock_account/
├── __init__.py
├── conftest.py                       # installs "stock_account" (transitively "stock" + "account")
├── test_valuation_standard_avco.py
├── test_valuation_fifo.py
└── test_valuation_report.py          # run standalone — shares the ledger-balance query pattern the
                                       #   accounting-test-isolation memory already flags for
                                       #   tests/accounting's report/balance tests

tests/benchmarks/test_inventory_perf.py     # PERF-001…004
tests/e2e/test_inventory_ui.py              # US1…US8 primary flows + WCAG (extends test_web_ui_a11y.py)
```

**Structure Decision**: Three addons matching the spec's explicit dependency chain
(`product` ← `stock` ← `stock_account` → `account`) rather than one monolithic addon, so a
deployment that wants Inventory without accounting integration can install `product` + `stock` alone
(no `account` dependency pulled in), exactly mirroring Odoo 19.0's own `stock`/`stock_account` module
boundary and the spec's Clarifications session. No new generic view type or menu-registration
mechanism is introduced — Inventory's UI work is entirely new *content* (menu file, view files) layered
on the list/form/kanban/calendar types and hardcoded per-app menu dispatch pattern 002/006 already
built.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Cross-addon `ALTER TABLE` on `product_category` from `stock_account` (ADR-033) instead of a normal `Field` declaration | `product.category` needs stock-valuation account properties once `stock_account` is installed, but `product` itself must carry zero dependency on `account` (Clarifications) | A new `stock.account.category.config` side-table avoids the raw DDL but adds a join to every valuation lookup and diverges from the codebase's one existing precedent (`account`→`res_partner`) for exactly this situation; giving `product` a dependency on `account` was already rejected in the spec's Clarifications |
| On-demand "Run Reordering Rules" REST action (FR-063a) instead of a background scheduler | Dodoo has no cron/scheduler subsystem today | Building one now would be new infrastructure far outside this feature's scope; `hr`'s own `/hr/cron/contract-expiry` manually-triggered REST endpoint is the exact precedent for "cron-shaped work without a cron subsystem," reused verbatim as `/stock/orderpoint/run` |
| `stock_account` monkey-patches `StockMove.action_set_state` at import time instead of `stock` calling it directly (ADR-034) | Valuation must post atomically when a move completes, but `stock` cannot import `stock_account` (reverse dependency) and no hook/event system exists in the codebase | A new core hook/event-bus would be genuinely new infrastructure for one integration point; a string-based dynamic/optional import inside `stock` was rejected because it still makes `stock`'s own source reason about `stock_account`'s presence, the exact coupling Clarifications ruled out |
