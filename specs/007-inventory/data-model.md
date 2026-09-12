# Data Model: Inventory

Field types are `dodoo.core.fields` classes (`Char`, `Integer`, `Boolean`, `Float`, `Date`,
`Datetime`, `Text`, `Many2one`, `One2many`, `Many2many`, `Selection`, `Monetary`, `Json`). Every
model gets `id` (PK), `create_date`, `write_date` automatically from `BaseModel._sa_table()`. FR
references are to `spec.md`.

## Area P1 — Product catalog, categories, variants, units of measure (`dodoo/addons/product/`)

### `product.category`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `name` | Char(128), required | |
| Hierarchy | `parent_id` | Many2one("product.category") | optional; FR-001 |
| Scope | `company_id` | Many2one("res.company") | nullable = shared (FR-001, FR-010) |

**Rules**: `parent_id` cycle rejected (same check style as `hr.department`). `company_id = NULL` ⇒
visible to all companies (FR-001).

**Not declared here**: `costing_method` and the three stock-valuation account properties are added
to this table by `stock_account` via `ALTER TABLE` (D1/ADR-033) — see the Area P3 — Valuation section
below. `product.category`'s own model file has no knowledge of costing or accounting, matching the
Clarifications' "`product` carries zero dependency on `account`" rule (and, transitively, no
knowledge of `stock` either).

### `uom.category` / `uom.uom`

| Model | Field | Type | Notes |
|---|---|---|---|
| `uom.category` | `name` | Char(64), required | e.g. Unit, Weight, Volume |
| `uom.uom` | `name` | Char(64), required | FR-002 |
| `uom.uom` | `category_id` | Many2one("uom.category"), required | |
| `uom.uom` | `uom_type` | Selection([reference, bigger, smaller]), required | exactly one `reference` per category |
| `uom.uom` | `ratio` | Float, required, default 1.0 | conversion factor to the category's reference unit |
| `uom.uom` | `rounding` | Float, default 0.01 | smallest representable quantity increment |

**Rules**: exactly one `reference` unit per `category_id` enforced at write time (reject a second
`reference` in the same category, mirroring `hr.leave.type`-style single-flag enforcement patterns).
Converting quantity `q` from unit `A` to unit `B` in the same category: `q * A.ratio / B.ratio` when
both are `bigger`/`smaller` relative to the same reference (FR-002/FR-003). Cross-category conversion
is rejected (FR-003).

### `product.template`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `name` | Char(256), required | |
| Identity | `barcode` | Char(64) | FR-004 |
| Classification | `category_id` | Many2one("product.category") | |
| Classification | `product_type` | Selection([goods, service]), default `goods` | FR-004; no "combo" (Clarifications) |
| Classification | `is_storable` ("track inventory") | Boolean, default False | applicable only when `product_type = goods` (FR-004/008) |
| UoM | `uom_id` | Many2one("uom.uom"), required | primary unit |
| UoM | `purchase_uom_id` | Many2one("uom.uom") | must share `category_id` with `uom_id` (FR-003) |
| Pricing | `list_price` | Monetary | sales price |
| Pricing | `standard_price` | Monetary | cost; standard-costing basis (FR-073) |
| Scope | `company_id` | Many2one("res.company") | nullable = shared (FR-010) |
| Scope | `active` | Boolean, default True | |

**Rules**: `is_storable` forced `False` and ignored when `product_type = service` (FR-008).
`purchase_uom_id.category_id` must equal `uom_id.category_id` (FR-003).

### `product.attribute` / `product.attribute.value` / `product.template.attribute.line`

| Model | Field | Type | Notes |
|---|---|---|---|
| `product.attribute` | `name` | Char(64), required | e.g. Color |
| `product.attribute.value` | `attribute_id` | Many2one("product.attribute"), required | |
| `product.attribute.value` | `name` | Char(64), required | e.g. Red |
| `product.template.attribute.line` | `template_id` | Many2one("product.template"), required | FR-005 |
| `product.template.attribute.line` | `attribute_id` | Many2one("product.attribute"), required | |
| `product.template.attribute.line` | `value_ids` | Many2many("product.attribute.value", relation_table="product_template_attribute_line_value_rel", column1="line_id", column2="value_id") | the subset of the attribute's values enabled for this template |

### `product.product` (variant)

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `template_id` | Many2one("product.template"), required | |
| Identity | `barcode` | Char(64) | overridable per variant (FR-007) |
| Pricing | `price_extra` | Monetary, default 0 | added on top of `template_id.list_price` (FR-007) |
| Composition | `attribute_value_ids` | Many2many("product.attribute.value", relation_table="product_product_attribute_value_rel", column1="product_id", column2="value_id") | the exact combination this variant represents |

**Rules** (FR-006): saving a template's attribute lines generates one `product.product` per element of
the Cartesian product of `value_ids` across all lines, skipping combinations that already have a
variant (idempotent regeneration on line edit). A template with zero attribute lines has exactly one
implicit variant (`attribute_value_ids = []`) auto-created with the template.

**Not declared here**: `tracking` (none/lot/serial) is added to this table by `stock` via
`ALTER TABLE` (same D1 idiom, one dependency level down — see Area P2 below), because enforcing "MUST
NOT change once the variant has any `stock.quant`/`stock.move.line` history" (FR-043) requires reading
`stock`'s own tables, which `product`'s model file must never do. Likewise the running average/FIFO
cost used by valuation (`stock_avg_cost`) is added by `stock_account`, not stored here — `product.
template.standard_price` above is only the catalog's plain, user-set cost (the standard-costing basis
and the FIFO/average *seed* value for a product's first receipt), never system-recomputed by
`product` itself.

**Indexes** (PERF-001): `CREATE INDEX idx_product_product_template ON product_product (template_id)`;
`CREATE INDEX idx_product_template_search ON product_template (company_id, category_id,
product_type)`; `CREATE INDEX idx_product_template_barcode ON product_template (barcode)`;
`CREATE INDEX idx_product_product_barcode ON product_product (barcode)`.

---

## Area P1 — Warehouses, locations, operation types (`dodoo/addons/stock/`) — ADR-029

### `stock.warehouse`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `name` | Char(128), required | |
| Identity | `code` | Char(16), required | short code, unique per company (FR-013) |
| Scope | `company_id` | Many2one("res.company"), required | |
| Address | `address` | Text | |
| Steps | `reception_steps` | Selection([one_step, two_steps, three_steps]), default `one_step` | FR-014 |
| Steps | `delivery_steps` | Selection([one_step, two_steps, three_steps]), default `one_step` | FR-014 |
| Locations | `view_location_id` | Many2one("stock.location") | the warehouse's root location |
| Locations | `stock_location_id` | Many2one("stock.location") | main internal stock location |

**Rules**: `code` unique within `company_id`. Creating/updating `reception_steps`/`delivery_steps`
runs `action_apply_steps` (ADR-029) — creates missing intermediate locations/operation types,
archives (never deletes) locations made redundant by a step decrease that already carry quant history
(D4).

### `stock.location`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `name` | Char(128), required | |
| Hierarchy | `parent_id` | Many2one("stock.location") | FR-015 |
| Usage | `usage` | Selection([internal, customer, vendor, inventory, production, transit, view]), required | FR-015 |
| Scope | `warehouse_id` | Many2one("stock.warehouse") | required when `usage = internal`, else null |
| Scope | `company_id` | Many2one("res.company") | derived from `warehouse_id` when set |
| Flags | `active` | Boolean, default True | D4 archival |
| Flags | `scrap_location` | Boolean, default False | marks the warehouse's default scrap target (US7) |

**Rules**: only `usage = internal` locations count toward company on-hand totals (FR-016). `parent_id`
cycle rejected.

### `stock.picking.type`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `name` | Char(128), required | e.g. "Receipts" |
| Identity | `code` | Selection([incoming, outgoing, internal]), required | FR-017 |
| Scope | `warehouse_id` | Many2one("stock.warehouse"), required | |
| Defaults | `default_location_src_id` | Many2one("stock.location") | |
| Defaults | `default_location_dest_id` | Many2one("stock.location") | |
| Naming | `sequence_prefix` | Char(16) | e.g. `WH/IN/` |
| Behaviour | `reservation_mode` | Selection([immediate, manual]), default `immediate` | FR-018/FR-025 — MUST NOT allow a "skip reservation" value |
| Behaviour | `backorder_policy` | Selection([ask, always, never]), default `ask` | FR-018/FR-028 |

**Indexes**: `CREATE INDEX idx_stock_location_parent ON stock_location (parent_id)`;
`CREATE INDEX idx_stock_location_warehouse_usage ON stock_location (warehouse_id, usage)`.

---

## Area P1 — Transfers and stock moves (`dodoo/addons/stock/`) — ADR-030

### `stock.picking`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `name` | Char(64) | assigned from the operation type's sequence on confirm |
| Routing | `picking_type_id` | Many2one("stock.picking.type"), required | FR-023 |
| Routing | `partner_id` | Many2one("res.partner") | optional (FR-024a, Clarifications) |
| Routing | `origin` | Char(256) | free-text link for backorders / cross-warehouse chains (D5) |
| Routing | `backorder_id` | Many2one("stock.picking") | set on a backorder pointing at its origin transfer |
| State | `state` | Selection([draft, waiting, confirmed, ready, done, cancelled]) | **derived**, not directly writable (ADR-030) |
| Dates | `scheduled_date` | Datetime | |
| Dates | `date_done` | Datetime | set when the last move validates |

### `stock.move`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `picking_id` | Many2one("stock.picking"), required | FR-024 |
| Product | `product_id` | Many2one("product.product"), required | |
| Quantity | `product_uom_qty` | Float, required | demanded quantity, in `product_uom_id` |
| Quantity | `product_uom_id` | Many2one("uom.uom"), required | |
| Routing | `location_src_id` | Many2one("stock.location"), required | |
| Routing | `location_dest_id` | Many2one("stock.location"), required | |
| State | `state` | Selection([draft, waiting, confirmed, ready, done, cancelled]) | authoritative state (ADR-030); the picking's is derived from this |
| Linking | `origin` | Char(256) | D5 |

### `stock.move.line`

| Group | Field | Type | Notes |
|---|---|---|---|
| Identity | `move_id` | Many2one("stock.move"), required | FR-026 |
| Quantity | `qty_done` | Float, required | actual quantity moved |
| Routing | `location_src_id` / `location_dest_id` | Many2one("stock.location") | MAY differ from the move's (putaway redirect, FR-057) |
| Tracking | `lot_id` | Many2one("stock.lot") | required when `product_id.tracking != none` (FR-045) |
| Tracking | `package_id` | Many2one("stock.quant.package") | destination package (FR-050) |
| Tracking | `result_package_id` | Many2one("stock.quant.package") | repackaging target (FR-053) |

**Rules**: `StockPicking.state` recomputed from its moves' states (ADR-030): `draft` (all draft) →
`waiting`/`confirmed` (some reserved, none done) → `ready` (all reservable moves reserved) → `done`
(all moves done) → `cancelled` (all cancelled). `StockMove.action_reserve` locks candidate
`stock.quant` rows `FOR UPDATE` (D2) before creating/updating `stock.move.line` rows up to the
available quantity. `StockMove.action_set_state(env, ids, target, uid, expected_state)` is the sole
manual-transition entrypoint (mirrors `hr_contract.py::action_set_state` exactly): rejects with
`transfer_state_conflict` + `log_conflict` when `expected_state` doesn't match the current row
(FR-035), else applies the transition and calls `log_transition` (FR-087). Validating with a reserved
quantity below demanded and `backorder_policy != never` offers `StockPicking.action_create_backorder`
(FR-028). A move line reducing an internal location's on-hand below zero is rejected (FR-029). Return
(FR-030) creates a new picking on the Returns-configured operation type with source/destination
swapped, quantities equal to the original done quantity (not the whole lot/package it may have been
part of — Edge Cases).

**Indexes** (PERF-002): `CREATE INDEX idx_stock_move_picking ON stock_move (picking_id)`;
`CREATE INDEX idx_stock_move_product_state ON stock_move (product_id, state)`;
`CREATE INDEX idx_stock_move_line_move ON stock_move_line (move_id)`.

---

## `stock.quant` (on-hand, shared by Areas P1/P2/P3)

| Group | Field | Type | Notes |
|---|---|---|---|
| Key | `product_id` | Many2one("product.product"), required | |
| Key | `location_id` | Many2one("stock.location"), required | |
| Key | `lot_id` | Many2one("stock.lot") | nullable — untracked products have no lot |
| Key | `package_id` | Many2one("stock.quant.package") | nullable |
| Quantity | `quantity` | Float, required, default 0 | on-hand at this key |
| Quantity | `reserved_quantity` | Float, required, default 0 | outgoing reservations against this key |
| Count | `counted_quantity` | Float | transient, set during a physical count (FR-037), cleared on apply |

**Rules**: unique on `(product_id, location_id, lot_id, package_id)` — a move upserts (increments/
decrements) rather than inserting a duplicate row for the same key. `available = quantity -
reserved_quantity`, never allowed negative for `usage = internal` locations except the
inventory-loss/adjustment counterpart of a count/scrap correction (FR-029, Edge Cases). Forecasted
quantity for a product = `Σ on-hand + Σ incoming (not-done moves into an internal location) − Σ
outgoing (not-done moves out of an internal location)` (FR-011, FR-063).

**Indexes** (PERF-002/003): `CREATE UNIQUE INDEX idx_stock_quant_key ON stock_quant (product_id,
location_id, COALESCE(lot_id, 0), COALESCE(package_id, 0))`; `CREATE INDEX idx_stock_quant_product ON
stock_quant (product_id)`.

---

## Area P2 — Physical inventory adjustments

No new model — an inventory count is a *view* over `stock.quant` (filtered by location/product/
category, `counted_quantity` made editable) plus an `apply_count` action
(`StockQuant.apply_count(env, quant_ids, uid)`) that, for every line where `counted_quantity !=
quantity`, creates a `stock.move`/`stock.move.line` pair between the location and its warehouse's
`scrap_location`-flagged (or a dedicated inventory-loss-usage) location for the delta and drives it to
done via `StockMove.action_set_state(env, [move_id], "done", uid=uid)` — the same choke point every
other "done" move goes through (ADR-030), which is exactly why `stock_account` only needs to hook that
one function (ADR-034/D6) to also value inventory adjustments — then sets `quantity =
counted_quantity` and clears `counted_quantity` (FR-038/039). Every applied line is recorded to a
lightweight `stock.inventory.adjustment.log` model (append-only) capturing `quant_snapshot`
(product/location/lot), `qty_before`, `qty_after`, `difference`, `uid`, `date` for FR-040's audit
trail.

### `stock.inventory.adjustment.log`

| Field | Type | Notes |
|---|---|---|
| `product_id`, `location_id`, `lot_id` | Many2one | snapshot of the counted key |
| `qty_before` / `qty_after` / `difference` | Float | FR-040 |
| `uid` | Many2one("res.users") | acting user |
| `move_id` | Many2one("stock.move") | the adjustment move created, if any (FR-039: none when difference = 0) |

---

## Area P2 — Lots, serial numbers, packages

### `product.product` extension column (added by `stock`, D1)

| Field | Type | Notes |
|---|---|---|
| `tracking` | VARCHAR(64) (Selection: none/lot/serial), default `none` | FR-043; added to the existing `product_product` table via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `stock/data/product_product_ext.py`, the same idiom as `stock_account`'s extension of `product.category` (D1/ADR-033) applied one dependency level down — `product` never declares this field itself |

**Rules**: meaningful only when the variant's template `is_storable`. Being absent from
`ProductProduct._fields`, `tracking` is invisible to `product.product.read()`/`.write()`;
`StockProductExt.set_tracking(env, product_id, tracking, uid)` (raw `UPDATE`, exposed via `POST
/stock/product/{id}/tracking`) is the sole write path and rejects a change once the variant has any
`stock.quant` row or `stock.move.line` history — a check only `stock` can make, which is exactly why
the field and its guard both live here rather than on `product.product`'s own model class.

### `stock.lot`

| Field | Type | Notes |
|---|---|---|
| `name` | Char(64), required | lot/serial number text |
| `product_id` | Many2one("product.product"), required | FR-044 |
| `company_id` | Many2one("res.company") | FR-049 |
| `expiration_date` | Date | optional |

**Rules**: unique on `(product_id, name)` (FR-044). A serial-tracked product's move line
(`product_id.tracking = serial`) MUST have `qty_done = 1` per `lot_id` and MUST NOT reuse a `lot_id`
that currently has any positive `stock.quant.quantity` for the same product elsewhere (FR-046).

### `stock.quant.package` / `stock.package.type`

| Model | Field | Type | Notes |
|---|---|---|---|
| `stock.package.type` | `name` | Char(64), required | |
| `stock.package.type` | `max_weight` | Float | optional |
| `stock.quant.package` | `name` | Char(64) | barcode/name, FR-050 |
| `stock.quant.package` | `package_type_id` | Many2one("stock.package.type") | optional |

**Rules**: `StockQuantPackage.move_package(env, package_id, dest_location_id, uid)` (FR-052) creates
one `stock.move.line` per quant currently keyed to the package, all sharing the same destination —
implemented as a thin wrapper generating an Internal Transfer picking rather than a bespoke bulk-update
path, so it stays inside the normal transfer/audit-logging pipeline.

**Indexes**: `CREATE INDEX idx_stock_lot_product_name ON stock_lot (product_id, name)`.

---

## Area P2 — Putaway rules, storage categories, routes, reordering rules — ADR-031 / ADR-032

### `stock.storage.category`

| Field | Type | Notes |
|---|---|---|
| `name` | Char(128), required | |
| `max_weight` | Float | optional |
| `max_packages` | Integer | optional |
| `allow_new_product` | Selection([always, same_product, same_lot]), default `always` | FR-055 |
| `location_ids` | Many2many("stock.location", relation_table="stock_storage_category_location_rel", column1="category_id", column2="location_id") | |

### `stock.putaway.rule`

| Field | Type | Notes |
|---|---|---|
| `location_src_id` | Many2one("stock.location"), required | FR-056 |
| `product_id` | Many2one("product.product") | mutually exclusive with `category_id` |
| `category_id` | Many2one("product.category") | |
| `location_dest_id` | Many2one("stock.location"), required | must be a descendant of `location_src_id` |
| `sequence` | Integer, default 10 | declaration-order tiebreak within the same specificity (FR-058) |

**Rules** (ADR-031): `StockPutawayRule.resolve_destination(env, product_id, source_location_id)` —
pure read, product-specific rules evaluated before category rules, ties broken by `sequence`; a
candidate destination is accepted only if `StockStorageCategory.has_capacity(env, location_id, ...)`
returns true for every storage category assigned to it, or the location carries no storage category
at all (unlimited capacity, FR-057/Edge Cases).

### `stock.route` / `stock.rule`

| Model | Field | Type | Notes |
|---|---|---|---|
| `stock.route` | `name` | Char(128), required | FR-060 |
| `stock.route` | `product_ids` / `category_ids` / `warehouse_ids` | Many2many (own junction tables) | applicability scope |
| `stock.rule` | `route_id` | Many2one("stock.route"), required | FR-061 |
| `stock.rule` | `sequence` | Integer | chain order within the route |
| `stock.rule` | `action` | Selection([move, resupply]) | FR-061 |
| `stock.rule` | `location_src_id` / `location_dest_id` | Many2one("stock.location"), required | chained via matching src/dest across rules (ADR-032) |
| `stock.rule` | `picking_type_id` | Many2one("stock.picking.type"), required | |

**Rules**: `location_dest_id` MUST NOT equal `location_src_id` directly or transitively within the
same route (FR-062). `StockRoute.get_applicable_route(env, product_id, warehouse_id)`: product-level
override → category-level → warehouse default (ADR-032).

### `stock.warehouse.orderpoint`

| Field | Type | Notes |
|---|---|---|
| `product_id` | Many2one("product.product"), required | FR-063 |
| `location_id` | Many2one("stock.location"), required | |
| `product_min_qty` / `product_max_qty` | Float, required | |
| `qty_multiple` | Float, default 1 | rounding for the replenishment quantity (FR-064) |

**Rules**: `StockWarehouseOrderpoint.run_reordering(env, orderpoint_ids=None, uid=None)` (FR-063a) —
the on-demand trigger; computes forecasted quantity per orderpoint, skips one already covered by an
existing incoming transfer (FR-065), else generates transfer(s) along
`StockRoute.get_applicable_route`'s rule chain (ADR-032) for `ceil((min − forecast) / qty_multiple) *
qty_multiple`, or reports `unresolved` when no route resolves to a supply source (FR-066).

**Indexes**: `CREATE INDEX idx_stock_orderpoint_product ON stock_warehouse_orderpoint (product_id,
location_id)`.

---

## Area P3 — Scrap

### `stock.scrap`

| Field | Type | Notes |
|---|---|---|
| `product_id` | Many2one("product.product"), required | FR-067 |
| `lot_id` | Many2one("stock.lot") | required when the product is tracked |
| `quantity` | Float, required | |
| `location_src_id` | Many2one("stock.location"), required | |
| `location_dest_id` | Many2one("stock.location"), required | the warehouse's scrap location |
| `reason` | Char(256) | free text |
| `state` | Selection([draft, done]) | FR-067 |
| `move_id` | Many2one("stock.move") | the generated stock move |

**Rules**: confirming rejects a `quantity` exceeding available on-hand at `location_src_id` (FR-068);
on success it creates `move_id` and drives it to done via `StockMove.action_set_state(env, [move_id],
"done", uid=uid)` (the ADR-030/ADR-034 choke point) before setting `stock.scrap.state = "done"`
itself. A done record is immutable (no `write`/`unlink` once `state = done`, mirroring `AccountMove`'s
posted-state guard) (FR-069).

---

## Area P3 — Valuation (`dodoo/addons/stock_account/`) — ADR-033

### `stock.valuation.layer`

| Field | Type | Notes |
|---|---|---|
| `product_id` | Many2one("product.product"), required | FR-072 |
| `stock_move_id` | Many2one("stock.move"), required | the move that created this layer |
| `quantity` | Float, required | signed: positive for incoming, negative for outgoing |
| `unit_cost` | Monetary, required | |
| `value` | Monetary, required | `quantity * unit_cost` at posting time; immutable once posted (D3) |
| `remaining_qty` | Float | FIFO only; mutable, decremented as later moves consume this layer |
| `remaining_value` | Monetary | FIFO only; mutable in lockstep with `remaining_qty` |
| `account_move_id` | Many2one("account.move"), required | the posted journal entry (FR-075) |
| `company_id` | Many2one("res.company"), required | |

**Rules** (ADR-033): `StockValuationLayer.value_move(env, move_id)` is invoked by `stock_account`'s
import-time wrapper around `StockMove.action_set_state` (ADR-034/D6) — never called from `stock`'s own
code — once per move driven to `"done"` for an `is_storable` product whose category's
`costing_method` is set: `standard` — value at the product's
plain `product.template.standard_price` (the catalog's own field, unchanged by valuation); `average`
— recompute the extension column `product_product.stock_avg_cost` as the new quantity-weighted
average across on-hand and value the move at the *pre-update* average for outgoing, the move's own
unit cost for incoming; `fifo` — incoming opens a new layer at the move's unit cost, outgoing
consumes open layers (`remaining_qty > 0`) oldest-`create_date`-first, splitting the last consumed
layer when needed (FR-073/074). Every layer's `value` posts a balanced `account.move`
(`move_type="entry"`) via `AccountMove.create` + line inserts + `AccountMove.action_post`, debiting/
crediting `product.category.property_stock_valuation_account_id` against
`property_stock_input_account_id` (incoming) or `property_stock_output_account_id` (outgoing), or an
inventory-loss account for count/scrap adjustments (FR-075). A non-`is_storable` product never
produces a layer or a journal entry (FR-076). Changing `costing_method` affects only layers created
afterward (FR-079, Edge Cases).

**Indexes** (PERF-004): `CREATE INDEX idx_svl_product_remaining ON stock_valuation_layer (product_id)
WHERE remaining_qty <> 0` (partial index — FIFO's "open layers" query never scans consumed layers);
`CREATE INDEX idx_svl_move ON stock_valuation_layer (stock_move_id)`.

### Extension columns added by `stock_account` (D1/ADR-033)

| Table (owning addon) | Column | Type | Notes |
|---|---|---|---|
| `product_category` (`product`) | `costing_method` | VARCHAR(64) (Selection: standard/average/fifo), default `standard` | FR-071 |
| `product_category` (`product`) | `property_stock_valuation_account_id` | INTEGER FK → `account_account.id` | FR-075 |
| `product_category` (`product`) | `property_stock_input_account_id` | INTEGER FK → `account_account.id` | FR-075 |
| `product_category` (`product`) | `property_stock_output_account_id` | INTEGER FK → `account_account.id` | FR-075 |
| `product_product` (`product`) | `stock_avg_cost` | NUMERIC(20,6), default 0 | running average cost for `average`-costing products; FIFO products don't use this column (their running value is the sum of open layers) |

All five are added by `stock_account/data/product_category_ext.py` /
`product_product_ext.py` via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, never as declared `Field`s
on `product`'s own model classes (D1). Because they are absent from `ProductCategory._fields` /
`ProductProduct._fields`, `BaseModel.create/read/write` silently ignore them (confirmed by
`account`'s identical, already-shipped `res_partner.property_account_*` columns, which the codebase
only ever touches via raw SQL) — they are read/written exclusively through
`GET`/`POST /stock_account/category/{id}/configure` (`contracts/stock-valuation.md`).

---

## Security groups & record rules (seeded)

Groups (`stock/security.py`, mirrors `hr/security.py`'s two-tier shape):

- `Inventory User` (`GROUP_USER`) — create/validate transfers, counts, lots/serials, packages, scrap
  within company scope (FR-081).
- `Inventory Manager` (`GROUP_MANAGER`, superset of User) — additionally manage warehouses, locations,
  operation types, putaway rules, storage categories, routes, reordering rules, costing-method
  configuration (FR-082).

Record rules (`stock/data/rules.py`, same `{name, model, domain, groups, perms}` shape as
`hr/data/rules.py`):

- `officer_full`-equivalent (`GROUP_MANAGER` only) on `stock.warehouse`, `stock.location`,
  `stock.picking.type`, `stock.putaway.rule`, `stock.storage.category`, `stock.route`, `stock.rule`,
  `stock.warehouse.orderpoint` — company-scoped (`$company_ids`), full CRUD (FR-081/082/083).
- `user_or_manager` (`GROUP_USER` + `GROUP_MANAGER`) on `stock.picking`, `stock.move`,
  `stock.move.line`, `stock.quant`, `stock.lot`, `stock.quant.package`, `stock.scrap` — company-scoped
  via their warehouse/location, full CRUD (FR-081).
- `catalog_read`-equivalent (both groups + any authenticated user, per Odoo's own "product catalog is
  broadly readable") on `product.category`, `uom.category`, `uom.uom`, `product.template`,
  `product.product` — company-scoped-or-shared domain identical to `hr`'s catalog-read shape
  (FR-010); write access restricted to `Inventory Manager` (`catalog_admin_write`-equivalent).
- `stock_valuation_layer` and the `product.category` extension columns: read gated to `Inventory
  Manager` (valuation is a manager-level reporting concern, FR-082); write happens only through
  `value_move`, never through a direct user-facing create/write endpoint (FR-084).

`base/http/__init__.py`'s `/web/core/info` response gains `stock_groups: list[str]` (`held` group
names starting with `"Inventory "`), following the exact `hr_groups` pattern, consumed by
`web/static/app.js`'s new `_stockHas`/`_renderStockMenu`.

## Entity relationship summary

```text
product.category ──< product.template ──< product.product ──< stock.quant >── stock.location ──< stock.warehouse
       │                                        │  │                              │  (parent hierarchy)
       │ (costing_method,                       │  └─< stock.lot                  └─< stock.picking.type ──< stock.picking ──< stock.move ──< stock.move.line
       │  +3 account cols                       │
       │  from stock_account)                   └─< stock.valuation.layer >── account.move (stock_account → account)
       │
uom.category ──< uom.uom >── product.template (uom_id / purchase_uom_id)

stock.storage.category >──< stock.location
stock.putaway.rule ── (product_id | category_id) × location_src_id → location_dest_id
stock.route ──< stock.rule (chained via location_src_id/location_dest_id) >── (product | category | warehouse)
stock.warehouse.orderpoint ── product_id × location_id, driven by stock.route

stock.scrap ── product_id [× lot_id] : location_src_id → location_dest_id (⊂ stock.move)
stock.quant.package >── stock.package.type ; referenced by stock.move.line (package_id / result_package_id)
```
