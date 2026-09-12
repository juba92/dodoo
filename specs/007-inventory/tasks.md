---

description: "Task list for Inventory implementation"
---

# Tasks: Inventory

**Input**: Design documents from `specs/007-inventory/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec mandates unit + integration + e2e coverage for every workflow
(SC-010) and the constitution requires ≥ 80% unit / 100% critical-path branch coverage.

**Organization**: Tasks are grouped by the eight user stories from spec.md, each independently
implementable and testable. `product` is built out entirely in US1. `stock` spans US2–US7.
`stock_account` is built out entirely in US8.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US8; Setup / Foundational / Polish have no story label
- Paths are repository-relative. dodoo addons live under `dodoo/addons/`; tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create `dodoo/addons/product/` skeleton: `__init__.py` (imports `http`, `models`; async `post_install` → `seed_product_data`), `__manifest__.py` (`{"name": "Product", "version": "1.0.0", "depends": ["base", "web"], "application": False}`), empty `models/__init__.py`, `http/__init__.py`, `data/__init__.py`, `static/views/` dir
- [ ] T002 Create `dodoo/addons/stock/` skeleton: `__init__.py` (imports `http`, `models`; async `post_install` → `seed_stock_data`), `__manifest__.py` (`{"name": "Inventory", "version": "1.0.0", "depends": ["product", "base", "web", "localization"], "application": True}`), empty `models/__init__.py`, `http/__init__.py`, `data/__init__.py`, `static/views/` dir
- [ ] T003 Create `dodoo/addons/stock_account/` skeleton: `__init__.py` (imports `http`, `models`; async `post_install` → `seed_stock_account_data`), `__manifest__.py` (`{"name": "Inventory Accounting", "version": "1.0.0", "depends": ["stock", "account"], "application": False}`), empty `models/__init__.py`, `http/__init__.py`, `data/__init__.py`
- [ ] T004 [P] Create test packages `tests/product/__init__.py`, `tests/stock/__init__.py`, `tests/stock_account/__init__.py`; add `tests/product/conftest.py`, `tests/stock/conftest.py`, `tests/stock_account/conftest.py` mirroring `tests/hr/conftest.py`'s fixtures (`pg_container`, `db_url`, `modules_installed` installing `"product"` / `"stock"` / `"stock_account"` respectively via `env.modules.install(name)`, `env`, `company_id`, `admin_uid`)
- [ ] T005 [P] Confirm `pyproject.toml` ruff/black globs already cover `dodoo/addons/product`, `dodoo/addons/stock`, `dodoo/addons/stock_account` (no change expected); run `ruff check` on the three addon skeletons
- [ ] T006 [P] File ADR files from plan.md text: `docs/adr/029-warehouse-step-topology.md`, `docs/adr/030-transfer-reservation-state-engine.md`, `docs/adr/031-putaway-storage-capacity-resolution.md`, `docs/adr/032-route-rule-replenishment-resolution.md`, `docs/adr/033-costing-method-valuation-engine.md`, `docs/adr/034-cross-addon-action-hooking.md` (title / status / context / decision / consequences + one-line threat note each)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [ ] T007 Create `dodoo/addons/product/validators.py`: `Payload` base (Pydantic v2, `extra="forbid"`, `protected_namespaces=()`), `validate(model_cls, payload) -> model`, `group_names(env, uid)`, `is_member(env, uid, name)`, `require_groups(env, uid, *names)` — the canonical copy (mirrors `hr/validators.py` exactly; `product` has no groups of its own but hosts these generic helpers since it has no dependency to re-export from)
- [ ] T008 Create `dodoo/addons/product/data/ir_model_sync.py`: `sync_ir_model(env, models: list[tuple[name, table]])` (own copy, mirrors `hr/data/ir_model_sync.py`)
- [ ] T009 Create `dodoo/addons/product/data/indexes.py`: `ensure_indexes(env, ddl: list[str])` (own copy, mirrors `hr/data/indexes.py`)
- [ ] T010 Create `dodoo/addons/product/data/seed.py`: `seed_product_data(env)` orchestrator calling `sync_ir_model` + `ensure_indexes` + a stub for per-area seed data (filled in T041); wire it from `product/__init__.py::post_install`
- [ ] T011 Create `dodoo/addons/product/http/__init__.py` skeleton: static mount + `json_ok`/`json_err` helpers matching `account/http`
- [ ] T012 [P] Create `dodoo/addons/stock/validators.py`: re-export `Payload`/`validate`/`group_names`/`is_member`/`require_groups` from `dodoo.addons.product.validators` (mirrors `fleet/validators.py` re-exporting from `hr`, since `stock` depends on `product`)
- [ ] T013 Create `dodoo/addons/stock/security.py`: `GROUP_USER = "Inventory User"`, `GROUP_MANAGER = "Inventory Manager"` (2-level nesting, mirrors `hr/security.py`); `seed_groups(env)`; `assign_inventory_group(env, uid, level)` inserting the level + all ancestors
- [ ] T014 Create `dodoo/addons/stock/data/groups.py` (calls `stock.security.seed_groups`) and `dodoo/addons/stock/data/rules.py` (empty `STOCK_RULES: list` registry + `apply(env)` + helper functions `manager_full(model)`, `user_or_manager_operate(model)`, `catalog_read(model)`, `catalog_admin_write(model)`, `valuation_manager_read(model)` per `data-model.md`'s Security section — per-model rule rows appended in each story phase)
- [ ] T015 [P] Create `dodoo/addons/stock/data/ir_model_sync.py` and `dodoo/addons/stock/data/indexes.py` that import and re-use the `product` helpers (mirrors `fleet/data/ir_model_sync.py` importing the `hr` helpers)
- [ ] T016 Create `dodoo/addons/stock/data/product_product_ext.py`: `async def add_tracking_column(env)` running `ALTER TABLE product_product ADD COLUMN IF NOT EXISTS tracking VARCHAR(64) NOT NULL DEFAULT 'none'` (D1, schema only — the write-guard/REST action is built in US5, T086/T089, but the column must exist before US3's move-line validation)
- [ ] T017 Create `dodoo/addons/stock/data/seed.py`: `seed_stock_data(env)` orchestrator calling, in order, `sync_ir_model`, `product_product_ext.add_tracking_column`, `groups.seed`, `ensure_indexes`, per-area seed stubs (filled in T051), `rules.apply`; wire it from `stock/__init__.py::post_install`
- [ ] T018 Create `dodoo/addons/stock/http/__init__.py` skeleton: static mount + `json_ok`/`json_err` helpers
- [ ] T019 Create `dodoo/addons/stock/_audit.py` with `log_transition(logger, *, model, record_id, actor_uid, event, frm=None, to=None, company_id=None, level=logging.INFO, **fields)` and `log_conflict(logger, *, model, record_id, event, expected, actual, actor_uid=None)` — exact copy of `hr/_audit.py`'s shape (FR-087, SEC-006: identifiers/states only, never free text)
- [ ] T020 Extend `dodoo/addons/base/http/__init__.py::core_info` (the `/web/core/info` route) to also return `stock_groups: list[str]` (`sorted(n for n in held if n.startswith("Inventory "))`), following the exact `hr_groups`/`fleet_manager` pattern already there
- [ ] T021 (BLOCKED on T052/T053 `stock-menu.js` + view modules from US2/US3) Register `#/inventory/*` routing in `dodoo/addons/web/static/app.js`: add the hash-prefix branch to `_renderSidebar` (mirrors the `#/hr` branch), add `_renderStockMenu(sidebar, currentHash)` / `_stockHas(requires)` (modelled on `_renderHrMenu`/`_hrHas`, reading `App.state.stockGroups` from `info.stock_groups`), update the navbar app-name switch; bump any client build/version marker the same way T018 in 006 did
- [ ] T022 [P] Create `dodoo/addons/stock_account/validators.py`: re-export `Payload`/`validate`/`group_names`/`is_member`/`require_groups` from `dodoo.addons.stock.validators` (mirrors `fleet` re-exporting from `hr`)
- [ ] T023 Create `dodoo/addons/stock_account/data/product_category_ext.py`: `async def add_valuation_columns(env)` running `ALTER TABLE product_category ADD COLUMN IF NOT EXISTS costing_method VARCHAR(64) NOT NULL DEFAULT 'standard'`, `ADD COLUMN IF NOT EXISTS property_stock_valuation_account_id INTEGER REFERENCES account_account(id)`, `ADD COLUMN IF NOT EXISTS property_stock_input_account_id INTEGER REFERENCES account_account(id)`, `ADD COLUMN IF NOT EXISTS property_stock_output_account_id INTEGER REFERENCES account_account(id)` (D1/ADR-033 — the `account`→`res_partner` idiom from `account/data/account_data.py`)
- [ ] T024 Create `dodoo/addons/stock_account/data/product_product_ext.py`: `async def add_stock_avg_cost_column(env)` running `ALTER TABLE product_product ADD COLUMN IF NOT EXISTS stock_avg_cost NUMERIC(20,6) NOT NULL DEFAULT 0` (D1/ADR-033)
- [ ] T025 Create `dodoo/addons/stock_account/data/seed.py`: `seed_stock_account_data(env)` orchestrator calling `product_category_ext.add_valuation_columns`, `product_product_ext.add_stock_avg_cost_column`, then seeding two new `account.account` rows ("Stock Interim (Received)" `asset_current`, "Stock Interim (Delivered)" `liability_current`) and one new `account.journal` row ("Inventory Valuation", type `general`), and setting every existing `product.category`'s `property_stock_valuation_account_id` to the already-seeded code-`1100` "Inventory" account via raw `UPDATE`; wire from `stock_account/__init__.py::post_install`
- [ ] T026 Create `dodoo/addons/stock_account/http/__init__.py` skeleton
- [ ] T027 [P] Test `tests/product/test_migrations.py`, `tests/stock/test_migrations.py`, `tests/stock_account/test_migrations.py` asserting every table and `ALTER TABLE`-added column from `data-model.md` exists after install (extended per story)

**Checkpoint**: addons install; groups/rules framework, validators, logging helper, `stock_groups`
info field, and the two schema-extension migrations all ready.

---

## Phase 3: User Story 1 — Product catalog, variants, units of measure (Priority: P1) 🎯 MVP

**Goal**: A searchable product catalog — categories, units of measure with conversion, templates
with attributes, and auto-generated variants — with no stock-tracking concepts leaking in for
services/untracked goods.

**Independent Test**: quickstart.md §1 — build a category hierarchy, a UoM category with
reference+derived units, a template with two attributes generating four variants, and a
non-tracking service product.

### Tests for User Story 1

- [ ] T028 [P] [US1] Unit test UoM conversion math (`ratio`-based, `reference` uniqueness per category, cross-category rejection, FR-002/003) in `tests/product/test_uom_conversion.py`
- [ ] T029 [P] [US1] Unit test variant Cartesian-product generation and idempotent regeneration on attribute-line edit (FR-006) in `tests/product/test_variant_generation.py`
- [ ] T030 [P] [US1] Integration test category hierarchy/cycle rejection, nullable-`company_id` shared-vs-scoped visibility (FR-001/010), and service/untracked products exposing no stock fields (FR-008) in `tests/product/test_access_rules.py`

### Implementation for User Story 1

- [ ] T031 [P] [US1] `product.category` model (`name`, `parent_id`, `company_id`) + cycle guard in `dodoo/addons/product/models/product_category.py`
- [ ] T032 [P] [US1] `uom.category` / `uom.uom` models + conversion helper (`convert(qty, from_uom, to_uom)`) + single-reference-per-category guard in `dodoo/addons/product/models/uom.py`
- [ ] T033 [US1] `product.template` model (name, barcode, `category_id`, `product_type`, `is_storable`, `uom_id`, `purchase_uom_id`, prices, `company_id`) + `is_storable` forced false for services + UoM-category-match guard in `dodoo/addons/product/models/product_template.py` (depends on T031, T032)
- [ ] T034 [US1] `product.attribute` / `product.attribute.value` / `product.template.attribute.line` (+ value M2M) models in `dodoo/addons/product/models/product_attribute.py` (depends on T033)
- [ ] T035 [US1] `product.product` model + variant Cartesian-product generation on attribute-line save (FR-006) in `dodoo/addons/product/models/product_product.py` (depends on T034)
- [ ] T036 [US1] REST actions `POST /product/template/{id}/attribute-lines/apply`, `GET /product/search`, `GET /product/{id}/uom-convert` in `dodoo/addons/product/http/products.py` (depends on T035)
- [ ] T037 [US1] Validators `ProductCategoryCreate`, `UomCreate`, `ProductTemplateCreate`, `ApplyAttributeLines` in `dodoo/addons/product/validators.py` (depends on T031–T035)
- [ ] T038 [US1] `catalog_read` / `catalog_admin_write` record rules for `product.category`, `uom.category`, `uom.uom`, `product.template`, `product.product` appended to `STOCK_RULES` in `dodoo/addons/stock/data/rules.py` (depends on T014, T031–T035)
- [ ] T039 [P] [US1] `dodoo/addons/product/static/views/product-category-list.js`, `product-template-form.js`, `product-variant-list.js` (reuse the `list.js`/`form.js` view types from 006)
- [ ] T040 [US1] Wire `product/data/seed.py`: seed UoM categories (Unit, Weight) + units (Unit/Dozen, Kilogram/Gram), a few product categories, and three sample products (a tracked good, an untracked good, a service) per FR-089
- [ ] T041 [US1] Indexes in `dodoo/addons/product/data/indexes.py`: `idx_product_product_template`, `idx_product_template_search (company_id, category_id, product_type)`, `idx_product_template_barcode`, `idx_product_product_barcode` (PERF-001)
- [ ] T042 [P] [US1] Add "Products", "Product Variants", "Product Categories", "Units of Measure" section to `dodoo/addons/stock/static/stock-menu.js`'s `STOCK_MENU` export (the app-level menu lives in `stock`, since `product` has no security group of its own)

**Checkpoint**: catalog is fully functional and testable standalone; every later story consumes it.

---

## Phase 4: User Story 2 — Warehouses, locations, operation types (Priority: P1)

**Goal**: Creating a warehouse auto-provisions its core locations and Receipts/Delivery
Orders/Internal Transfers/Returns operation types per its step configuration (ADR-029).

**Independent Test**: quickstart.md §2 — create a two-step-delivery warehouse and confirm its
topology; add a child location and confirm it's usable.

### Tests for User Story 2

- [ ] T043 [P] [US2] Unit test `action_apply_steps` topology generation (one/two/three-step, idempotent re-run, archive-not-delete of a history-bearing location per D4) in `tests/stock/test_warehouse_topology.py`
- [ ] T044 [P] [US2] Integration test location `usage`-type on-hand counting (FR-016), parent-cycle rejection, operation-type defaults, and company scope across warehouse/location/picking-type in `tests/stock/test_warehouse_access.py`

### Implementation for User Story 2

- [ ] T045 [P] [US2] `stock.location` model (`name`, `parent_id`, `usage`, `warehouse_id`, `company_id`, `active`, `scrap_location`) + cycle guard in `dodoo/addons/stock/models/stock_location.py`
- [ ] T046 [US2] `stock.warehouse` model + `action_apply_steps` (ADR-029: creates missing locations/operation-types per `reception_steps`/`delivery_steps`, archives redundant history-bearing locations per D4) in `dodoo/addons/stock/models/stock_warehouse.py` (depends on T045)
- [ ] T047 [US2] `stock.picking.type` model (`name`, `code`, `warehouse_id`, defaults, `sequence_prefix`, `reservation_mode`, `backorder_policy`) in `dodoo/addons/stock/models/stock_picking_type.py` (depends on T046)
- [ ] T048 [US2] REST actions `GET /stock/warehouse/{id}/topology`, `POST /stock/warehouse/{id}/apply-steps`, plus warehouse/location/picking-type CRUD in `dodoo/addons/stock/http/warehouses.py` (depends on T045–T047)
- [ ] T049 [US2] Validators `WarehouseCreate`, `LocationCreate`, `PickingTypeCreate` in `dodoo/addons/stock/validators.py` (depends on T045–T047)
- [ ] T050 [US2] `manager_full` record rules for `stock.warehouse`, `stock.location`, `stock.picking.type` appended to `STOCK_RULES` (depends on T014, T045–T047)
- [ ] T051 [US2] Wire `stock/data/seed.py`'s per-area stub (T017): create the default warehouse "WH" via `action_apply_steps`, replacing the placeholder (FR-089) (depends on T046)
- [ ] T052 [P] [US2] `dodoo/addons/stock/static/views/warehouse-form.js`, `location-list.js` (reuse `form.js`/`list.js`)
- [ ] T053 [P] [US2] Add "Warehouses", "Locations", "Operation Types" section to `stock-menu.js`

**Checkpoint**: warehouses/locations/operation types are independently testable and seeded.

---

## Phase 5: User Story 3 — Receipts, delivery orders, internal transfers, returns (Priority: P1) 🎯 MVP

**Goal**: The core move-stock transaction: confirm → reserve → validate → done, with backorders,
returns, and cancellation, safe under concurrent reservation (ADR-030, D2).

**Independent Test**: quickstart.md §3 — receive 10, deliver 4 (full reservation), deliver 20 against
6 on hand (partial + backorder), return a done delivery, and confirm a stale `validate()` conflicts.

### Tests for User Story 3

- [ ] T054 [P] [US3] Unit test `stock.move`'s `_TRANSITIONS` table and `action_set_state`'s from-state conflict guard (mirrors `hr_contract.py`) in `tests/stock/test_transfer_reservation.py`
- [ ] T055 [P] [US3] Unit test `action_reserve`'s `FOR UPDATE` reservation math — full, partial, zero availability (D2) — in `tests/stock/test_transfer_reservation.py` (sequential after T054, same file)
- [ ] T056 [P] [US3] Integration test full receipt→reserve→validate flow updating on-hand, and a delivery with insufficient stock producing a partial validate + backorder offer (FR-028) in `tests/stock/test_transfer_lifecycle.py`
- [ ] T057 [P] [US3] Integration test the Return action (source/destination swap, exact originally-moved quantity) and Cancel (reservation released, on-hand unaffected) in `tests/stock/test_transfer_lifecycle.py` (sequential after T056)
- [ ] T058 [P] [US3] Integration test two concurrent `validate()` calls with the same `expected_state` — the second is rejected with a conflict, no double on-hand decrement (FR-035) — in `tests/stock/test_transfer_concurrency.py`

### Implementation for User Story 3

- [ ] T059 [US3] `stock.quant` model (`product_id`, `location_id`, `lot_id`, `package_id`, `quantity`, `reserved_quantity`, `counted_quantity`) with the `(product_id, location_id, lot_id, package_id)` upsert key in `dodoo/addons/stock/models/stock_quant.py`
- [ ] T060 [US3] `stock.move` model + `action_reserve` (`SELECT ... FOR UPDATE` on candidate quants, D2) + `action_set_state(env, ids, target, uid, expected_state)` (the single "done" choke point, ADR-030/034) in `dodoo/addons/stock/models/stock_move.py` (depends on T059)
- [ ] T061 [US3] `stock.move.line` model (`move_id`, `qty_done`, `location_src_id`/`location_dest_id`, `lot_id`, `package_id`, `result_package_id`) in `dodoo/addons/stock/models/stock_move_line.py` (depends on T060)
- [ ] T062 [US3] `stock.picking` model (`picking_type_id`, `partner_id` optional per FR-024a, `origin`, `backorder_id`, `scheduled_date`, `date_done`) with **derived** `state` (computed from its moves, ADR-030), `action_create_backorder`, and the Return action (FR-030) in `dodoo/addons/stock/models/stock_picking.py` (depends on T060, T061)
- [ ] T063 [US3] REST actions `POST /stock/picking/{id}/{confirm,validate,cancel,return}` in `dodoo/addons/stock/http/transfers.py` (depends on T062)
- [ ] T064 [US3] REST action `GET /stock/product/{id}/forecast` (on-hand/reserved/incoming/outgoing/forecasted, FR-011/034) in `dodoo/addons/stock/http/transfers.py` (depends on T059)
- [ ] T065 [US3] Validators `TransferCreate`, `TransferValidate`, `TransferCancel`, `MoveLineUpdate` in `dodoo/addons/stock/validators.py` (depends on T060–T062)
- [ ] T066 [US3] `user_or_manager_operate` record rules for `stock.picking`, `stock.move`, `stock.move.line`, `stock.quant` appended to `STOCK_RULES` (depends on T014, T059–T062)
- [ ] T067 [US3] Wire FR-029's negative-on-hand rejection into `action_reserve`/move-line validation, and FR-087 structured logging (`stock/_audit.py`) into every `action_set_state` call (depends on T019, T060)
- [ ] T068 [P] [US3] `dodoo/addons/stock/static/views/transfer-kanban.js` (by operation-type/state, reuses `kanban.js`) and `transfer-form.js`
- [ ] T069 [P] [US3] Add "Receipts", "Delivery Orders", "Internal Transfers", "Returns" section to `stock-menu.js`
- [ ] T070 [US3] Indexes in `stock/data/indexes.py`: `idx_stock_move_picking`, `idx_stock_move_product_state`, `idx_stock_move_line_move`, `idx_stock_quant_key` (unique), `idx_stock_quant_product` (PERF-002/003)
- [ ] T071 [US3] Unblock T021: complete `_renderStockMenu`/`_stockHas` + `#/inventory` sidebar dispatch in `web/static/app.js` now that `stock-menu.js` and the transfer/warehouse/product views exist (depends on T039, T042, T052, T053, T068, T069)

**Checkpoint**: US1+US2+US3 (all P1) form a complete MVP — receive, deliver, and internally
transfer stock end to end.

---

## Phase 6: User Story 4 — Physical inventory adjustments (Priority: P2)

**Goal**: Count on-hand quantities and apply corrections that route through the same
`action_set_state` choke point as every other move.

**Independent Test**: quickstart.md §4 — set a counted quantity below/above/equal to on-hand and
confirm the resulting adjustment (or its absence).

### Tests for User Story 4

- [ ] T072 [P] [US4] Unit test `apply_count`'s delta computation, including the FR-039 no-op-when-equal case, in `tests/stock/test_inventory_adjustment.py`
- [ ] T073 [P] [US4] Integration test the count set→apply flow updating on-hand and writing a `stock.inventory.adjustment.log` row (FR-040) in `tests/stock/test_inventory_adjustment.py` (sequential after T072)

### Implementation for User Story 4

- [ ] T074 [US4] `stock.inventory.adjustment.log` model (`product_id`, `location_id`, `lot_id`, `qty_before`, `qty_after`, `difference`, `uid`, `move_id`) in `dodoo/addons/stock/models/stock_inventory_adjustment.py`
- [ ] T075 [US4] `StockQuant.apply_count(env, quant_ids, uid)` (creates the adjustment move and drives it to done via `action_set_state`, FR-038) + count-set staging in `dodoo/addons/stock/models/stock_quant.py` (depends on T059, T060, T074)
- [ ] T075a [US4] `user_or_manager_operate` record rule for `stock.inventory.adjustment.log` appended to `STOCK_RULES`, scoped via the dotted-path domain `["location_id.warehouse_id.company_id", "in", "$company_ids"]` (ADR-028's relational-traversal engine, FR-042/SEC-003) (depends on T014, T074)
- [ ] T076 [US4] REST actions `POST /stock/inventory/count/set`, `POST /stock/inventory/count/apply` in `dodoo/addons/stock/http/inventory.py` (depends on T075)
- [ ] T077 [US4] Validators `CountSet`, `CountApply` in `dodoo/addons/stock/validators.py` (depends on T075)
- [ ] T078 [P] [US4] `dodoo/addons/stock/static/views/inventory-count-list.js`
- [ ] T079 [P] [US4] Add "Physical Inventory" entry to `stock-menu.js`

**Checkpoint**: counts are independently testable on top of US3.

---

## Phase 7: User Story 5 — Lots, serial numbers, packages (Priority: P2)

**Goal**: Optional per-product lot/serial tracking and package-level handling, with full
traceability.

**Independent Test**: quickstart.md §5 — receive 3 serials, deliver 1, confirm per-serial on-hand;
pack two units, move the package, confirm both quants travel together; look up a serial's history.

### Tests for User Story 5

- [ ] T080 [P] [US5] Unit test serial uniqueness-while-on-hand guard and lot on-hand accumulation (FR-044/046) in `tests/stock/test_lots_serials.py`
- [ ] T081 [P] [US5] Integration test tracking-mode immutability once quant/move history exists (FR-043) and the `set_tracking` raw-SQL write path in `tests/stock/test_lots_serials.py` (sequential after T080)
- [ ] T082 [P] [US5] Integration test package move (all quants relocate together, FR-052) and traceability-lookup completeness for a lot/serial/package (FR-048/054) in `tests/stock/test_packages.py`

### Implementation for User Story 5

- [ ] T083 [US5] `stock.lot` model (`name`, `product_id`, `company_id`, `expiration_date`), unique on `(product_id, name)`, in `dodoo/addons/stock/models/stock_lot.py`
- [ ] T084 [US5] `stock.quant.package` / `stock.package.type` models in `dodoo/addons/stock/models/stock_package.py` (depends on T059)
- [ ] T085 [US5] Extend `stock.move.line` validation: require `lot_id` when `product_id.tracking != none` (FR-045); serial-tracked lines require `qty_done == 1` and reject a `lot_id` currently on hand elsewhere for the same product (FR-046) — in `dodoo/addons/stock/models/stock_move_line.py` (depends on T061, T083)
- [ ] T086 [US5] `StockProductExt.set_tracking(env, product_id, tracking, uid)` guard (raw `UPDATE`, rejects once the variant has any `stock.quant` row or `stock.move.line` history) in `dodoo/addons/stock/models/product_product_ext.py` (depends on T016, T059, T061)
- [ ] T087 [US5] `StockQuantPackage.move_package` (generates an Internal Transfer picking, FR-052) + repackaging via `result_package_id` (FR-053) in `dodoo/addons/stock/models/stock_package.py` (depends on T084, T062)
- [ ] T088 [US5] Traceability query helpers `get_lot_events` / `get_package_events` (chronological transfer list, FR-048/054) in `stock_lot.py` / `stock_package.py` (depends on T083, T084, T085, T087)
- [ ] T089 [US5] REST routes `GET /stock/traceability/{lot,package}/{id}`, `POST /stock/package/{id}/move`, `GET`/`POST /stock/product/{id}/tracking` in `dodoo/addons/stock/http/traceability.py` (depends on T086–T088)
- [ ] T090 [US5] Validators `LotCreate`, `PackageMove`, `TrackingUpdate` in `dodoo/addons/stock/validators.py` (depends on T083, T084, T086)
- [ ] T091 [US5] `user_or_manager_operate` record rules for `stock.lot`, `stock.quant.package` appended to `STOCK_RULES` (depends on T014, T083, T084)
- [ ] T092 [P] [US5] Index `idx_stock_lot_product_name` in `stock/data/indexes.py` (depends on T083)
- [ ] T093 [P] [US5] `dodoo/addons/stock/static/views/traceability-view.js`
- [ ] T094 [P] [US5] Add "Lots & Serial Numbers", "Packages" section to `stock-menu.js`

**Checkpoint**: traceability is independently testable on top of US3.

---

## Phase 8: User Story 6 — Putaway rules, storage categories, routes, reordering rules (Priority: P2)

**Goal**: Automatic destination redirection on receipt (ADR-031) and on-demand,
route-driven replenishment (ADR-032, FR-063a).

**Independent Test**: quickstart.md §6 — a capacity-limited storage category redirects successive
receipts to different locations; a reordering rule below minimum produces a replenishment transfer,
with no duplicate on a second run.

### Tests for User Story 6

- [ ] T095 [P] [US6] Unit test `resolve_destination` precedence (product before category, `sequence` tiebreak) and `has_capacity` (ADR-031) in `tests/stock/test_putaway_storage.py`
- [ ] T096 [P] [US6] Unit test route rule-chain validation (no self-referential destination, ADR-032/FR-062) and `get_applicable_route` precedence in `tests/stock/test_routes_reordering.py`
- [ ] T097 [P] [US6] Integration test putaway redirection end to end on a receipt, including the capacity-exhaustion fallback (FR-057/Edge Cases) in `tests/stock/test_putaway_storage.py` (sequential after T095)
- [ ] T098 [P] [US6] Integration test `run_reordering`: deficit → transfer proposal, duplicate suppression (FR-065), and unresolved-route reporting (FR-066) in `tests/stock/test_routes_reordering.py` (sequential after T096)

### Implementation for User Story 6

- [ ] T099 [US6] `stock.storage.category` model + `has_capacity(env, location_id, incoming_qty, incoming_package)` (ADR-031) in `dodoo/addons/stock/models/stock_storage_category.py` (depends on T045)
- [ ] T100 [US6] `stock.putaway.rule` model + `resolve_destination(env, product_id, source_location_id)` (ADR-031, FR-057/058) in `dodoo/addons/stock/models/stock_putaway_rule.py` (depends on T099)
- [ ] T101 [US6] Wire putaway resolution into move-line destination assignment at receipt time in `dodoo/addons/stock/models/stock_move.py` (depends on T100, T060)
- [ ] T102 [US6] `stock.route` / `stock.rule` models + `get_applicable_route(env, product_id, warehouse_id)` + chain-cycle rejection (ADR-032, FR-060–062) in `dodoo/addons/stock/models/stock_route.py`
- [ ] T103 [US6] `stock.warehouse.orderpoint` model + `run_reordering(env, orderpoint_ids=None, uid=None)` (ADR-032, FR-063a/064/065/066) in `dodoo/addons/stock/models/stock_orderpoint.py` (depends on T102, T062)
- [ ] T104 [US6] REST routes `GET /stock/putaway/resolve`, `POST /stock/orderpoint/run`, plus CRUD for storage-category/putaway/route/rule/orderpoint in `dodoo/addons/stock/http/routes.py` (depends on T099–T103)
- [ ] T105 [US6] Validators `StorageCategoryCreate`, `PutawayRuleCreate`, `OrderpointCreate`, `RunReordering` in `dodoo/addons/stock/validators.py` (depends on T099–T103)
- [ ] T106 [US6] `manager_full` record rules for `stock.storage.category`, `stock.putaway.rule`, `stock.route`, `stock.rule`, `stock.warehouse.orderpoint` appended to `STOCK_RULES` (depends on T014, T099–T103)
- [ ] T107 [P] [US6] Index `idx_stock_orderpoint_product` in `stock/data/indexes.py` (depends on T103)
- [ ] T108 [P] [US6] `dodoo/addons/stock/static/views/putaway-rule-list.js`, `route-form.js`, `orderpoint-list.js` (reuse `list.js`/`form.js`)
- [ ] T109 [P] [US6] Add "Putaway Rules", "Storage Categories", "Routes", "Reordering Rules" section to `stock-menu.js`

**Checkpoint**: all P1+P2 stories (US1–US6) are independently functional.

---

## Phase 9: User Story 7 — Scrap (Priority: P3)

**Goal**: Write off damaged/lost stock as a narrow, auditable document.

**Independent Test**: quickstart.md §7 — scrap 2 of 10 on hand, confirm the split; over-scrap is
rejected.

### Tests for User Story 7

- [ ] T110 [P] [US7] Unit test scrap-confirm's quantity-exceeds-on-hand rejection (FR-068) and post-done immutability (FR-069) in `tests/stock/test_scrap.py`
- [ ] T111 [P] [US7] Integration test scrap confirmation updating on-hand at both the source and scrap locations in `tests/stock/test_scrap.py` (sequential after T110)

### Implementation for User Story 7

- [ ] T112 [US7] `stock.scrap` model + confirm action (creates its `stock.move` and drives it to done via `action_set_state`, ADR-030/034) in `dodoo/addons/stock/models/stock_scrap.py` (depends on T059, T060)
- [ ] T113 [US7] REST action `POST /stock/scrap/{id}/confirm` in `dodoo/addons/stock/http/scrap.py` (depends on T112)
- [ ] T114 [US7] Validator `ScrapCreate` in `dodoo/addons/stock/validators.py` (depends on T112)
- [ ] T115 [US7] `user_or_manager_operate` record rule for `stock.scrap` appended to `STOCK_RULES`, scoped via the dotted-path domain `["location_src_id.warehouse_id.company_id", "in", "$company_ids"]` (FR-070/SEC-003) (depends on T014, T112)
- [ ] T116 [P] [US7] `dodoo/addons/stock/static/views/scrap-form.js`
- [ ] T117 [P] [US7] Add "Scrap" entry to `stock-menu.js`

**Checkpoint**: scrap is independently testable on top of US3.

---

## Phase 10: User Story 8 — Inventory valuation & accounting integration (Priority: P3)

**Goal**: Cost every tracked move (standard/average/FIFO) and post it as a balanced journal entry,
without `stock` ever depending on or referencing `stock_account` (ADR-033/034).

**Independent Test**: quickstart.md §8 — standard-cost a receipt, confirm the layer and journal
entry; switch to average and confirm the recomputed cost; reconcile the report to the ledger.

### Tests for User Story 8

- [ ] T118 [P] [US8] Unit test standard-costing valuation math in `tests/stock_account/test_valuation_standard_avco.py`
- [ ] T119 [P] [US8] Unit test average-costing `stock_avg_cost` recompute math in `tests/stock_account/test_valuation_standard_avco.py` (sequential after T118)
- [ ] T120 [P] [US8] Unit test FIFO layer consumption and splitting math (D3) in `tests/stock_account/test_valuation_fifo.py`
- [ ] T121 [P] [US8] Integration test receipt→layer→balanced `account.move` posting for each costing method (FR-073–075) in `tests/stock_account/test_valuation_standard_avco.py` / `test_valuation_fifo.py` (sequential)
- [ ] T122 [P] [US8] Integration test the valuation report reconciling to `AccountAccount.get_balance` (FR-078) in `tests/stock_account/test_valuation_report.py` — **run standalone**, not batched with other DB-sharing test files, per the project's `[[accounting-test-isolation]]` memory
- [ ] T123 [P] [US8] Integration test a non-`is_storable` product never producing a layer or journal entry (FR-076) in `tests/stock_account/test_valuation_standard_avco.py` (sequential after T118)

### Implementation for User Story 8

- [ ] T124 [US8] `stock.valuation.layer` model (`product_id`, `stock_move_id`, `quantity`, `unit_cost`, `value`, `remaining_qty`, `remaining_value`, `account_move_id`, `company_id`) in `dodoo/addons/stock_account/models/stock_valuation_layer.py` (depends on T023, T024)
- [ ] T125 [US8] `StockValuationLayer.value_move(env, move_id)` — standard/average/FIFO dispatch per `product.category.costing_method`, FIFO oldest-first consumption with splitting (D3), and the `AccountMove.create` → line inserts → `AccountMove.action_post` posting sequence crediting/debiting the category's three account properties (FR-073–075, ADR-033) — in `stock_valuation_layer.py` (depends on T124)
- [ ] T126 [US8] Wrap `StockMove.action_set_state` at import time in `dodoo/addons/stock_account/__init__.py`: call the original, then on a successful transition to `"done"` for an `is_storable` product call `value_move` (ADR-034/D6) (depends on T060, T125)
- [ ] T127 [US8] REST routes `GET`/`POST /stock_account/category/{id}/configure` (raw-SQL read/write of the four extension columns, FR-079), `GET /stock/valuation/report`, `GET /stock/valuation/reconcile` in `dodoo/addons/stock_account/http/valuation.py` (depends on T023, T124, T125)
- [ ] T128 [US8] Validator `CategoryValuationConfig` in `dodoo/addons/stock_account/validators.py` (depends on T127)
- [ ] T129 [US8] `valuation_manager_read` record rule for `stock.valuation.layer` appended to `STOCK_RULES` (FR-084) (depends on T014, T124)
- [ ] T130 [P] [US8] Index `idx_svl_product_remaining` (partial, `WHERE remaining_qty <> 0`) and `idx_svl_move` in `dodoo/addons/stock_account/data/indexes.py` (PERF-004) (depends on T124)
- [ ] T131 [P] [US8] Add "Valuation Report" entry to `stock-menu.js`

**Checkpoint**: all eight user stories are independently functional; the Inventory feature is
feature-complete per spec.md.

---

## Phase 11: Polish & Cross-Cutting Concerns

- [ ] T132 [P] Documentation: verify `docs/adr/029`–`034` match the as-built code; update any drifted rationale (Principle V)
- [ ] T133 Code cleanup: remove the Foundational-phase seed/rule stubs once every story's real seed data and rules have replaced them; remove dead code (Principle I)
- [ ] T134 Performance benchmarking: implement `tests/benchmarks/test_inventory_perf.py` asserting PERF-001 (catalog search < 500 ms @ 20k variants), PERF-002 (transfer confirm < 500 ms @ 100 lines), PERF-003 (forecast < 300 ms @ 100k quants), PERF-004 (valuation report < 1 s @ 50k layers); verify no > 10% regression on features 001–006's existing benchmarks (Principle IV)
- [ ] T135 [P] Additional unit tests to close any coverage gap in `tests/product/`, `tests/stock/`, `tests/stock_account/`; verify ≥ 80% unit / 100% critical-path coverage (Principle II)
- [ ] T136 Security hardening: OWASP Top 10 review pass across every new REST route (SEC-001–007), confirm no raw-SQL string interpolation, secrets scan (Principle III)
- [ ] T137 Accessibility audit (WCAG 2.1 AA): contrast, keyboard nav (including the putaway/route/reordering editors), screen-reader labels, no colour-only status, on every new view (ACC-001–004, Principle VI)
- [ ] T138 Dependency audit: confirm zero new third-party dependencies were introduced; lock file unchanged (Principle VII)
- [ ] T139 Observability review: verify every workflow transition across all eight stories emits the FR-087 structured log entry (SC-008); confirm SEC-006 (no PII/free-text in logs) holds for scrap reasons and count notes (Principle IX)
- [ ] T140 Run `quickstart.md` end to end (all 11 sections); confirm every Definition-of-Done checkbox passes and all CI gates pass with no bypasses (Principle VIII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phase 3–10)**: All depend on Foundational. US1 (Phase 3) blocks nothing but is
  consumed by every later story (every story's product references need the catalog). US2 (Phase 4)
  must precede US3 (needs warehouses/locations/operation types to exist). US3 (Phase 5) is the
  reservation/state-engine foundation US4/US5/US6/US7 all build directly on top of (their moves route
  through `action_set_state`). US8 (Phase 10) is the only story with a hard cross-addon ordering
  constraint: it can only be implemented once `stock.move`'s `action_set_state` choke point (T060)
  exists, but is otherwise independent of US4–US7.
- **Polish (Phase 11)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependency on other stories
- **US2 (P1)**: Can start after Foundational — no dependency on other stories (independent of US1's
  product catalog; a warehouse doesn't need a product to exist)
- **US3 (P1)**: Needs US2's warehouses/locations/operation types and US1's products to exist as FK
  targets, but is otherwise a self-contained story
- **US4/US5/US7 (P2/P3)**: Each needs US3's `stock.quant`/`stock.move`/`action_set_state` machinery;
  independent of each other
- **US6 (P2)**: Needs US2 (locations) and US3 (moves); independent of US4/US5/US7
- **US8 (P3)**: Needs US3's `action_set_state` choke point; independent of US4–US7's own content
  (though it values moves those stories' actions also generate)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services/actions before HTTP routes before views/menu wiring
- Record rules can be added any time after the model exists (T014 must precede all of them)
- Story complete before moving to the next priority (or work stories P1 → P2 → P3 in parallel if
  staffed, per Foundational's shared readiness)

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (T004, T005, T006, T012, T015, T022, T027)
- Once Foundational completes, US1 and US2 can start in parallel (no shared files); US3 must wait for
  both
- Once US3 completes, US4, US5, US6, and US7 can all proceed in parallel (different files); US8 can
  start as soon as T060 (part of US3) lands, in parallel with US4–US7
- All tests for a user story marked [P] can run in parallel unless noted "sequential" (same file)
- Models within a story marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test UoM conversion math in tests/product/test_uom_conversion.py"
Task: "Unit test variant Cartesian-product generation in tests/product/test_variant_generation.py"
Task: "Integration test category hierarchy + catalog visibility in tests/product/test_access_rules.py"

# Launch independent models for User Story 1 together:
Task: "product.category model in dodoo/addons/product/models/product_category.py"
Task: "uom.category/uom.uom models in dodoo/addons/product/models/uom.py"
```

## Parallel Example: User Stories 4, 5, 6, 7 (after US3 completes)

```bash
Task: "Physical inventory adjustments (US4) — tests/stock/test_inventory_adjustment.py + stock/models/stock_inventory_adjustment.py"
Task: "Lots, serials, packages (US5) — tests/stock/test_lots_serials.py + stock/models/stock_lot.py"
Task: "Putaway/storage/routes/reordering (US6) — tests/stock/test_putaway_storage.py + stock/models/stock_storage_category.py"
Task: "Scrap (US7) — tests/stock/test_scrap.py + stock/models/stock_scrap.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1–3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3 (US1) and Phase 4 (US2) — in parallel if staffed
4. Complete Phase 5 (US3)
5. **STOP and VALIDATE**: quickstart.md §1–3 — a receipt, a delivery, a return, all working
6. Deploy/demo if ready — this is the smallest slice that reproduces "move stock in, out, and around"

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 + US2 → US3 → Test independently → Deploy/Demo (MVP!)
3. US4, US5, US6, US7 → Test each independently → Deploy/Demo (in any order, or in parallel)
4. US8 → Test independently → Deploy/Demo (valuation layered on top, changes nothing observable
   about US3–US7's own behaviour)
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers, once Foundational is done:

- Developer A: US1 (product) then US4 (counts)
- Developer B: US2 then US3 (the P1 core, sequential since US3 needs US2)
- Developer C: US5 (traceability) once US3 lands
- Developer D: US6 (routes/reordering) once US3 lands
- Developer E: US7 (scrap) then US8 (valuation, needs US3's `action_set_state`)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- `product`/`stock`/`stock_account` never import "up" the dependency chain — every cross-addon
  extension is either an `ALTER TABLE` (D1/ADR-033) or an import-time function wrap (D6/ADR-034),
  never a reverse Python import
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence
